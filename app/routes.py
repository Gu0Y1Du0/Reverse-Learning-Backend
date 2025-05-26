import base64
import re
import bcrypt
import json
import logging
from typing import Union, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import RedirectResponse, FileResponse
from sqlalchemy.orm import sessionmaker

from .config import ENVPATH, DATABASE_URL
from .offline_TXT_Question import text_response
from .offline_VL_Get import vl_question
from .services import call_qwen, call_qwen_vl, call_deepseek_r1_distill_download
from .models import Student, ConversationScore, Teacher, AdministratorMechanism
from .database import (export_studentname_to_excel, engine, create_or_add_class, dissolve_class,
                       delete_member_from_class, join_class, get_class_details, get_frequency,
                       get_studentname, get_teachername, add_in_list, add_student_to_class_in_list)
from .utils import mkdir, encode_image, extract_json_content

router = APIRouter()

# 创建会话工厂
SessionLocal = sessionmaker(bind=engine)

# --- 通用业务 ---
# 登录请求模型
class LoginRequest(BaseModel):
    username: str
    password: str
    userrole: str  # 用户身份

# 学生注册模型
class StudentRegisterRequest(BaseModel):
    username: str
    password: str
# 教师注册
class TeacherRegisterRequest(BaseModel):
    username: str
    password: str
    Invite: str     # 邀请码

# 修改密码
class ChangePasswordRequest(BaseModel):
    username: str
    oldpassword: str
    newpassword: str
    userrole: str

# 多轮对话请求模型
class ChatRequest(BaseModel):
    studentname: str  # 用户名，用于区分用户会话
    prompt: str    # 用户输入的问题

class ViewRequest(BaseModel):
    studentname: str
    file: str   # 图片的Base64格式

# 学习建议模型
class AdviceRequest(BaseModel):
    studentname: str
    prompt: str

# 资源下载模型
class GetsourceRequest(BaseModel):
    studentname: str
    sourcenumber: int

# 存储用户对话历史（简单实现，使用内存中的字典）
conversation_history = {}

# 创建文件路径
filepath = ENVPATH

# 登录
@router.post("/login")
async def login(request: LoginRequest):
    try:
        # 连接数据库
        db = SessionLocal()
        # 查询用户
        if request.userrole == "student":
            user = db.query(Student).filter(Student.studentname == request.username).first()
            if not user:
                raise HTTPException(status_code=401, detail="学生不存在")
            # 验证密码
            if not bcrypt.checkpw(request.password.encode('utf-8'), user.password_hash.encode('utf-8')):
                raise HTTPException(status_code=401, detail="学生用户名或密码错误")
            # 确保用户文件夹存在
            user_folder = Path(ENVPATH) / request.username
            mkdir(user_folder)
            # 读取用户的聊天记录
            file_path = user_folder / f"{request.username}_chat_history.txt"
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    conversation_history[request.username] = []
                    for line in lines:
                        if line.startswith("用户: "):
                            conversation_history[request.username].append(line.strip()[4:])
                        elif line.startswith("AI: "):
                            conversation_history[request.username].append(line.strip()[3:])
            else:
                conversation_history[request.username] = []
            return {"status": "success", "message": "学生登录成功"}
        elif request.userrole == "teacher":
            user = db.query(Teacher).filter(Teacher.teachername == request.username).first()
            if not user:
                raise HTTPException(status_code=401, detail="教师不存在")
            # 验证密码
            if not bcrypt.checkpw(request.password.encode('utf-8'), user.password_hash.encode('utf-8')):
                raise HTTPException(status_code=401, detail="教师用户名或密码错误")
            # 确保用户文件夹存在
            user_folder = Path(ENVPATH) / request.username
            mkdir(user_folder)
            return {"status": "success", "message": "教师登录成功"}
    except Exception as e:
        print(f"在登录时发生错误: {str(e)}")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后再试")

# 学生注册
@router.post("/student-register")
async def register(request: StudentRegisterRequest):
    # 连接数据库
    db = SessionLocal()
    # 检查用户名是否已存在
    student = db.query(Student).filter(Student.studentname == request.username).first()
    if student:
        raise HTTPException(status_code=400, detail="学生用户名已存在，请选择其他用户名")
    # 加密密码
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(request.password.encode('utf-8'), salt).decode('utf-8')
    # 创建新用户
    new_student = Student(
        studentname=request.username,
        password_hash = hashed_password
    )
    try:
        db.add(new_student)
        db.commit()
        db.refresh(new_student)
        return {"status": "success", "message": "学生身份注册成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

@router.post("/teacher-register")
async def register(request: TeacherRegisterRequest):
    db = SessionLocal()
    InviteCode = db.query(AdministratorMechanism).filter(AdministratorMechanism.InvitationCode == request.Invite).first()
    if not InviteCode:
        raise HTTPException(status_code=400, detail="邀请码错误")
    teacher = db.query(Teacher).filter(Teacher.teachername == request.username).first()
    if teacher:
        raise HTTPException(status_code=400, detail="教师用户名已存在，请选择其他用户名")
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(request.password.encode('utf-8'), salt).decode('utf-8')
    new_teacher = Teacher(
        teachername=request.username,
        password_hash = hashed_password
    )
    try:
        db.add(new_teacher)
        db.commit()
        db.close()
        return {"status": "success", "message": "教师身份注册成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

# 修改密码
@router.post("/change-password")
async def change_password(request: ChangePasswordRequest):
    db = SessionLocal()
    try:
        if request.userrole == "student":
            user = db.query(Student).filter(Student.studentname == request.username).first()
            if not bcrypt.checkpw(request.oldpassword.encode('utf-8'), user.password_hash.encode('utf-8')):
                db.close()
                raise HTTPException(status_code=401, detail="旧密码错误")
            # 加密密码
            salt = bcrypt.gensalt()
            hashed_password = bcrypt.hashpw(request.newpassword.encode('utf-8'), salt).decode('utf-8')
            db.query(Student).filter(Student.studentname == request.username).update({"password_hash": hashed_password})
            db.commit()
            return {"status": "success", "detail": "密码修改成功"}
        elif request.userrole == "teacher":
            user = db.query(Teacher).filter(Teacher.teachername == request.username).first()
            if not bcrypt.checkpw(request.oldpassword.encode('utf-8'), user.password_hash.encode('utf-8')):
                db.close()
                raise HTTPException(status_code=401, detail="旧密码错误")
            salt = bcrypt.gensalt()
            hashed_password = bcrypt.hashpw(request.newpassword.encode('utf-8'), salt).decode('utf-8')
            db.query(Teacher).filter(Teacher.teachername == request.username).update({"password_hash": hashed_password})
            db.commit()
            return {"status": "success", "detail": "密码修改成功"}
    except SQLAlchemyError as e:
        db.rollback()  # 回滚事务
        raise HTTPException(status_code=500, detail=f"数据库操作失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")
    finally:
        db.close()  # 确保关闭会话

# 千问问答
@router.post("/chat")
async def qwenchat(request: ChatRequest):
    try:
        # 定义 Preprompt
        Preprompt = (
            "你是一个侧重逆向学习的教育助手，负责分析用户的对话内容，有逻辑地引导学生正向积极地学习。"
            "请按照以下 JSON 格式返回结果："
            "{"
            '    "用户画像": {'
            '        "学段": "小学/初中/高中/大学",'
            '        "教材": "如人教版、苏教版等",'
            '        "困难的知识点": ["知识点1", "知识点2"]'
            '    },'
            '    "学习状态分数": {'
            '        "学习深度": 0,'
            '        "响应及时性": 0,'
            '        "自我修正主动性": 0,'
            '        "情感参与度": 0,'
            '        "学习状态总分": 0'
            '    },'
            '    "回复内容": "用教师语气,对用户输入的回复"'
            "}"
            "计算学习状态分数规则如下(均为10分制，无法测出就返回0)："
            "学习深度(分数占比30％)：基于问题链长度（平均值）。"
            "响应及时性(分数占比20％)：基于用户的平均提问时间差。"
            "自我修正主动性(分数占比25％)：基于用户对错误的自我修正次数。"
            "情感参与度(分数占比25％)：基于用户对话中的情感词汇密度。"
        )
        # 获取用户印记 建立数据库连接
        username = request.studentname
        prompt = request.prompt
        # 确保初始化数据存储
        if username not in conversation_history:
            conversation_history[username] = []
        # 创建用户文件夹和用户画像文件路径
        user_folder = Path(ENVPATH) / username
        mkdir(user_folder)
        user_profile_path = user_folder / f"{username}_profile.txt"
        # 加载用户画像（如果存在）
        user_profile = ""
        if user_profile_path.exists():
            with open(user_profile_path, "r", encoding="utf-8") as f:
                user_profile = f.read()
        # 调用AI时，将Preprompt，用户画像拼接到用户输入
        full_prompt_for_ai = f"{Preprompt}\n\n用户画像：\n{user_profile}\n\n用户输入内容:\n{prompt}"
        try:
            response_text = call_qwen(full_prompt_for_ai, conversation_history[username])
            print("AI 返回的内容:", response_text)
        except Exception as e:
            print(f"服务器错误: {str(e)}")
            raise HTTPException(status_code=500, detail=f"调用 AI 失败: {str(e)}")

        # 解析 JSON 数据
        try:
            response_text = response_text.replace("\\", "\\\\")
            ai_response = json.loads(response_text)
            # 解析用户画像
            if "用户画像" in ai_response:
                user_profile_data = ai_response["用户画像"]
                grade = user_profile_data.get("学段", "")
                textbook = user_profile_data.get("教材", "")
                difficult_topics = user_profile_data.get("困难的知识点", [])
                # 更新用户画像
                user_profile_content = (
                    f"学生信息：\n"
                    f"- 学段：{grade}\n"
                    f"- 教材：{textbook}\n"
                )
                if difficult_topics:
                    user_profile_content += f"- 困难的知识点：{'， '.join(difficult_topics)}\n"
                    # 将用户画像写入文件
                with open(user_profile_path, "w", encoding="utf-8") as f:
                    f.write(user_profile_content)
                    # 解析学习状态分数
            if "学习状态分数" in ai_response:
                score_data = ai_response["学习状态分数"]
                question_depth = score_data.get("学习深度", 0)
                response_timeliness = score_data.get("响应及时性", 0)
                correction_proactivity = score_data.get("自我修正主动性", 0)
                emotional_engagement = score_data.get("情感参与度", 0)
                total_score = score_data.get("学习状态总分", 0)

                # 输出分数
                print(question_depth, response_timeliness, correction_proactivity, emotional_engagement, total_score)

                # 存入数据库
                db = SessionLocal()
                new_score = ConversationScore(
                    studentname=username,
                    question_depth=question_depth,
                    response_timeliness=response_timeliness,
                    correction_proactivity=correction_proactivity,
                    emotional_engagement=emotional_engagement,
                    total_score=total_score
                )
                db.add(new_score)
                db.commit()
                db.close()
            # 提取回复内容
            reply_content = ai_response.get("回复内容", "").strip()
            response_text = reply_content  # 将回复内容作为最终返回值

        except json.JSONDecodeError as e:
            print(f"AI 返回的内容不是有效的 JSON 格式: {str(e)}")
            raise HTTPException(status_code=500, detail=f"AI 返回的内容不是有效的 JSON 格式: {str(e)}")
        conversation_history[username].append(f"用户: {prompt}")
        conversation_history[username].append(f"AI: {response_text}")
        # 写入文件（仅保存用户原始输入和 AI 回复）
        file_path = user_folder / f"{username}_chat_history.txt"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"用户: {prompt}\n\nAI: {response_text}\n\n")

        return {"status": "success", "response": response_text}

    except Exception as e:
        print(f"服务器错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

# 数据库获取最新得分
@router.get("/evaluation/{studentname}")
async def get_evaluation(studentname: str):
    # 从数据库获取用户的最新评估数据
    try:
        db = SessionLocal()
        latest_score = (
            db.query(ConversationScore)
            .filter(ConversationScore.studentname == studentname)
            .order_by(ConversationScore.timestamp.desc())
            .first()
        )
        # 未提取到
        if not latest_score:
            raise HTTPException(status_code=404, detail="用户评估数据不存在")
        # 整理并返回最新的评分数据
        result = {
            "timestamp": str(latest_score.timestamp),
            "追问深度": latest_score.question_depth,
            "反馈及时性": latest_score.response_timeliness,
            "修正主动性": latest_score.correction_proactivity,
            "情感参与度": latest_score.emotional_engagement,
            "综合评分": latest_score.total_score
        }

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")
    finally:
        db.close()

# 图片拍照解题(大模型识别图片并解题)
@router.post("/upload-image")
async def qwenview(request: ViewRequest):
    logging.info(f"Received request: {request}")
    try:
        username = request.studentname
        if not request.studentname:
            raise HTTPException(status_code=400, detail="Username is required.")
        file = request.file
        # 检查文件类型是否为图片
        if not file.startswith("data:image/"):
            return JSONResponse(status_code=400, content={"message": "只支持图片文件！"})
        prompt = (
            "请按照以下 JSON 格式返回结果，不要使用markdown格式，需保证转化为JSON后数学符号、换行符号不影响或干扰包解析："
            "{"
            '    "题目": "识别到的完整题目，如果是选择题，需要加入选项",'
            '    "正确答案": {'
            '        "详细解析": "详细的解答过程",'
            '        "考察知识点": ["知识点1", "知识点2"]'
            "    }"
            "}"
        )
        # 提取 Base64 数据和 MIME 类型
        match = re.match(r"data:(image/(\w+));base64,(.*)", file)
        if not match:
            return JSONResponse(status_code=400, content={"status": "error", "message": "无效的图片数据！"})

        mime_type, file_extension, base64_data = match.groups()
        file_extension = file_extension.lower()
        if file_extension.lower() not in ["png", "jpg", "jpeg"]:
            return JSONResponse(status_code=400, content={"status": "error", "message": "不支持的图片格式！"})

        # 解码 Base64 数据
        base64_data = base64_data.replace("\n", "").replace("\r", "")  # 清理空白字符
        image_data = base64.b64decode(base64_data)

        # 生成唯一的文件名（避免文件名冲突）
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_filename = f"{timestamp}.{file_extension}"

        # 创建用户文件夹和用户画像文件路径
        user_folder = Path(ENVPATH) / username
        mkdir(user_folder)
        problem_folder = user_folder / "Problem"
        mkdir(problem_folder)

        # 拼接完整图片路径
        image_path = problem_folder / unique_filename
        # 读取文件内容并保存到指定路径
        with open(image_path, "wb") as f:
            f.write(image_data)
        # 调用模型
        try:
            # 将xxxx/eagle.png替换为你本地图像的绝对路径
            Image_path = encode_image(image_path)
            response_text = call_qwen_vl(Image_path, prompt, file_extension)
            if not response_text:
                raise ValueError("模型未返回有效响应")
            # 解析 JSON 数据
            try:
                # 提取 content 字段
                ai_response = extract_json_content(response_text)
                # 提取题目部分
                question = ai_response.get("题目", "").strip()
                if not question:
                    raise ValueError("无法从模型响应中提取题目内容")
                # 提取正确答案部分
                correct_answer = ai_response.get("正确答案", {})
                detailed_explanation = correct_answer.get("详细解析", "").strip()
                knowledge_points = correct_answer.get("考察知识点", [])
                # 存储题目和答案
                date_str = datetime.now().strftime("%Y-%m-%d")
                user_problem_path = user_folder / f"{username}_problem.md"
                with open(user_problem_path, "a", encoding="utf-8") as f:
                    f.write(f"日期: {date_str}\n\n")
                    f.write(f"题目: {question}\n\n")
                    f.write(f"正确答案:\n")
                    f.write(f"- 详细解析: {detailed_explanation}\n")
                    f.write(f"- 考察知识点: {'，'.join(knowledge_points)}\n\n")
                # 返回标准化的响应
                return {
                    "status": "success",
                    "message": "图片解析成功",
                    "response": {
                        "题目": question,
                        "正确答案": {
                            "详细解析": detailed_explanation,
                            "考察知识点": knowledge_points
                        }
                    }
                }
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=500, detail=f"模型返回的内容不是有效的 JSON 格式: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"模型调用失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"拍照搜题报错: {str(e)}")

# --- Student业务 ---    资源下载
@router.post("/student-get-source")
async def student_get_source(request: GetsourceRequest):
    username = request.studentname
    sourcenumber = request.sourcenumber
    user_folder = Path(ENVPATH) / username
    try:
        match sourcenumber:
            # 聊天记录
            case 1:
                file_path = user_folder / f"{username}_chat_history.txt"
                filename = f"{username}_chat_history.txt"
                return FileResponse(file_path, media_type="application/octet-stream", filename=filename)
            # 错题
            case 2:
                file_path = user_folder / f"{username}_problem.md"
                filename = f"{username}_problem.md"
                return FileResponse(file_path, media_type="application/octet-stream", filename=filename)
            # 学习建议
            case 3:
                call_deepseek_r1_distill_download(username)
                file_path = user_folder / f"{username}_advice.txt"
                filename = f"{username}_advice.txt"
                return FileResponse(file_path, media_type="application/octet-stream", filename=filename)
            # 导出学习状态分数记录execl表
            case 4:
                file_path = user_folder / f"{username}_conversation_scores.xlsx"
                filename = f"{username}_conversation_scores.xlsx"
                export_studentname_to_excel(DATABASE_URL, username, file_path)
                return FileResponse(file_path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=filename)
    except Exception as e:
        raise  HTTPException(status_code=500, detail=f"资源下载报错: {str(e)}")

# 从 MySQL 数据库获取询问次数和时间
@router.post("/recentlyask/{studentname}")
async def recentlyAsk(studentname: str):
    try:
        db = SessionLocal()
        # 获取当前日期，不包含时间部分
        current_date = datetime.now().date()
        # 计算七天前的日期
        seven_days_ago = current_date - timedelta(days=7)
        # 查询选定用户在最近七天内的插入记录
        result = (
            db.query(
                func.date(ConversationScore.timestamp).label("date"),  # 按日期分组
                func.count(ConversationScore.id).label("count")  # 统计每天的插入次数
            )
            .filter(
                ConversationScore.studentname == studentname,  # 筛选用户名
                ConversationScore.timestamp >= seven_days_ago  # 筛选最近七天
            )
            .group_by(func.date(ConversationScore.timestamp))  # 按日期分组
            .order_by(func.date(ConversationScore.timestamp))  # 按日期排序
            .all()
        )
        # 将结果转换为列表字典格式
        stats = [{"date": row.date.strftime('%Y-%m-%d'), "count": row.count} for row in result]
        # 关闭数据库会话
        db.close()
        # 返回 JSON 响应
        return {"username": studentname, "recent_stats": stats}
    except Exception as e:
        raise  HTTPException(status_code=500, detail=f"获取提问次数和日期出错: {str(e)}")

# 调试显示
@router.get("/")
async def redirect_to_docs():
    return RedirectResponse(url="/docs")

# --- Teacher业务 ---
# 创建班级/拉学生进班级
class CreateClassRequest(BaseModel):
    teacherid: int
    student_identifier: Union[int, str]
    classname: str

# 解散班级
class DissolveClassRequest(BaseModel):
    teacherid: int
    classname: str

# 教师踢出成员
class DeleteMemberFromClassRequest(BaseModel):
    teacher_identifier: Union[int, str]
    student_identifier: Union[int, str]
    classname: str

# 教师获取班级学生成员列表
class GetClassDetailsRequest(BaseModel):
    teacherid: int
    classname: str

# 获取学生提问频率
class GetStudentFrequencyRequest(BaseModel):
    student_identifier: Union[int, str]
    start: datetime
    end: datetime

# 获取学生画像
class GetStudentSourceRequest(BaseModel):
    student_identifier: Union[int, str]
    sourcenumber: int

# --- 5-23 教师层 补充教师功能 ---
# 删除教师
class DeleteTeacherRequest(BaseModel):
    teacher_identifier: Union[int, str]
    Invite: str
# 教师
class TeacherIn(BaseModel):
    teachername: str
    password: str
# 教师账号批量导入
class AddTeacherInListRequest(BaseModel):
    teacherlist: List[TeacherIn]

# 学生批量导入班级
class AddStudentToClassInListRequest(BaseModel):
    teacher_identifier: Union[int, str]
    classname: str
    studentidlist: List[int]

# 删除教师
@router.post("/delete-teacher")
async def delete_teacher(request: DeleteTeacherRequest):
    db = SessionLocal()
    InviteCode = db.query(AdministratorMechanism).filter(AdministratorMechanism.InvitationCode == request.Invite).first()
    if not InviteCode:
        raise HTTPException(status_code=400, detail="邀请码错误")
    # 验证教师权限
    if isinstance(request.teacher_identifier, int):
        teacher = db.query(Teacher).get(request.teacher_identifier)
    else:
        teacher = db.query(Teacher).filter(Teacher.teachername == request.teacher_identifier).first()
    if not teacher:
        raise HTTPException(status_code=400, detail="该教师不存在或未注册")
    try:
        db.delete(teacher)
        db.commit()
        db.close()
        return {"status": "success", "message": f"注销教师{teacher.teachername}成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

# 批量导入教师
@router.post("/add-teacher-in-list")
async def add_teacher_in_list(request: AddTeacherInListRequest):
    try:
        result = add_in_list(DATABASE_URL, "Teacher", request.teacherlist)
        if result:
            return {"status": "success", "message": "成功批量增加教师账号"}
        else:
            return {"status": "fail", "message": "批量增加失败，部分账号可能已加入"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

# 批量导入学生到指定班级
@router.post("/add-student-to-class-list")
async def add_student_to_class_list(request: AddStudentToClassInListRequest):
    try:
        result = add_student_to_class_in_list(DATABASE_URL, request.teacher_identifier, request.classname, request.studentidlist)
        if result:
            return {"status": "success", "message": f"成功批量增加学生到{request.classname}"}
        else:
            return {"status": "fail", "message": "批量增加失败"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

# 创建班级/拉学生进入班级
@router.post("/teacher-create-class-or-add-class")
async def teacher_create_class_or_add_class(request: CreateClassRequest):
    try:
        result = create_or_add_class(DATABASE_URL, request.teacherid, request.student_identifier, request.classname)
        if result:
            return {"status": "success", "message": f"{request.classname}: 添加一名学生"}
        elif not result:
            return {"status": "fail", "message": f"{request.classname}: 创建失败或添加学生失败"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="函数逻辑错误或网络问题: {str(e)}")

# 解散班级
@router.post("/teacher-dissolve-class")
async def teacher_dissolve_class(request: DissolveClassRequest):
    try:
        result = dissolve_class(DATABASE_URL, request.teacherid, request.classname)
        if result:
            return {"status": "success", "message": f"{request.classname}: 已被解散"}
        elif not result:
            return {"status": "fail", "message": f"{request.classname}: 解散失败，请检查班级是否存在"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"函数逻辑错误或网络问题: {str(e)}")

# 教师移出成员
@router.post("/teacher-delete-member-from-class")
async def teacher_delete_member_from_class(request: DeleteMemberFromClassRequest):
    try:
        result = delete_member_from_class(DATABASE_URL, request.teacher_identifier, request.student_identifier, request.classname)
        if result:
            return {"status": "success", "message": f"{request.classname}: 已移出该学生"}
        elif not result:
            return {"status": "fail", "message": f"{request.classname}: 解散失败"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"函数逻辑错误或网络问题: {str(e)}")

# 教师获取班级学生成员列表
@router.post("/teacher-get-class-details")
async def teacher_get_class_details(request: GetClassDetailsRequest):
    try:
        result = get_class_details(DATABASE_URL, request.teacherid, request.classname)
        if result["students"]:
            return {"status": "success", "data": result}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"{str(ve)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")

# 教师获取学生提问频率
@router.post("/teacher-get-student-frequency")
async def teacher_get_student_frequency(request: GetStudentFrequencyRequest):
    try:
        result = get_frequency(DATABASE_URL, request.student_identifier, request.start, request.end)
        if result["studentname"] != 0:
            return {"status": "success", "data": result}
        else:
            raise HTTPException(status_code=400, detail="依赖函数出现问题")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"{str(ve)}")
    except Exception as e:
        # 记录完整错误日志
        # logger.error(f"获取班级详情失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="服务器内部错误")

# 教师获取学生文件     学习建议/画像/错题
@router.post("/teacher-get-student-file")
async def teacher_get_student_file(request: GetStudentSourceRequest) -> FileResponse:
    studentname = get_studentname(DATABASE_URL, request.student_identifier)
    username = studentname
    sourcenumber = request.sourcenumber
    try:
        if not studentname:
            raise HTTPException(status_code=400, detail="学生信息不存在")
        user_folder = Path(ENVPATH) / f"{username}"
        match sourcenumber:
            # 聊天记录
            case 1:
                file_path = user_folder / f"{username}_chat_history.txt"
                filename = f"{username}_chat_history.txt"
                return FileResponse(file_path, media_type="application/octet-stream", filename=filename)
            # 错题
            case 2:
                file_path = user_folder / f"{username}_problem.md"
                filename = f"{username}_problem.md"
                return FileResponse(file_path, media_type="application/octet-stream", filename=filename)
            # 学习建议
            case 3:
                call_deepseek_r1_distill_download(username)
                file_path = user_folder / f"{username}_advice.txt"
                filename = f"{username}_advice.txt"
                return FileResponse(file_path, media_type="application/octet-stream", filename=filename)
            # 导出学习状态分数记录execl表
            case 4:
                file_path = user_folder / f"{username}_conversation_scores.xlsx"
                filename = f"{username}_conversation_scores.xlsx"
                export_studentname_to_excel(DATABASE_URL, username, file_path)
                return FileResponse(file_path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=filename)
    except Exception as e:
        raise  HTTPException(status_code=500, detail=f"资源下载报错: {str(e)}")

# 允许上传的文件类型（按需扩展）
ALLOWED_EXTENSIONS = {"txt", "png", "jpg", "jpeg", "md"}
# 教师上传文件
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
@router.post("/teacher-upload-file")
async def teacher_upload_file(teacher_identifier: Union[int, str], target_is_student: bool, target_identifier: Union[int, str], file: UploadFile = File(...)):
    teachername = get_teachername(DATABASE_URL, teacher_identifier)
    try:
        # 验证文件类型
        if not allowed_file(file.filename):
            raise HTTPException(status_code=400, detail="不支持的文件类型")
        if target_is_student:
            target = get_studentname(DATABASE_URL, target_identifier)
            target_folder = Path(ENVPATH) / f"{target}"
            mkdir(target_folder)
            file_path = Path(ENVPATH) / f"{target}" / f"{file.filename}"
        else:
            user_folder = Path(ENVPATH) / f"{teachername}"
            mkdir(user_folder)
            file_path = Path(ENVPATH) / f"{teachername}" / f"{file.filename}"
        # 保存文件
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        return {"status": "success", "filename": f"{file.filename}"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")

# --- Student业务补充 ---
# 学生主动加入班级
class JoinClassRequest(BaseModel):
    teacher_identifier: Union[int, str]
    student_identifier: Union[int, str]
    classname: str

class TextQueryRequest(BaseModel):
    # 用户问题（原始问题）
    prompt: str
    # 最大生成长度
    max_new_tokens: int = 615
    # 系统消息模板（可选，默认为 TIR 模板）
    system_message: Optional[str] = (
        "Please reason step by step, and put your final answer within \\boxed{}."
    )

class PhotographQueryRequest(BaseModel):
    # Local File Path/Base64 Encoded Image/Image URL
    Photograph: str     # data:image;base64,/9j/... 或 路径 或 网址
    # 视觉 token 数
    vl_max_new_tokens: int = 256
    # 数学 token 数
    math_max_new_tokens: int = 615
    # 系统消息模板
    system_message: Optional[str] = (
        "请你描述一下这张图片。"
    )

class QueryResponse(BaseModel):
    response: str

class StudentIn(BaseModel):
    studentname: str
    password: str
class AddStudentInListRequest(BaseModel):
    studentlist: List[StudentIn]

# 学生主动加入班级
@router.post("/student-join-class")
async def student_join_class(request: JoinClassRequest):
    try:
        result = join_class(DATABASE_URL, request.teacher_identifier, request.student_identifier, request.classname)
        if result:
            return {"status": "success", "message": f"{request.classname}: 已加入"}
        elif not result:
            return {"status": "fail", "message": f"{request.classname}: 加入失败"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"函数逻辑错误或网络问题: {str(e)}")

# 学生离线询问
@router.post("/student-offline-text-question", response_model=QueryResponse)
async def student_offline_text_question(request: TextQueryRequest):
    try:
        # 解题
        response = text_response(request.system_message, request.prompt, request.max_new_tokens)
        # 返回结果
        return {"response": response}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/student-photograph-question", response_model=QueryResponse)
async def student_photograph_question(request: PhotographQueryRequest):
    try:
        # 获取图片题目内容
        question = vl_question(request.Photograph, request.system_message, request.vl_max_new_tokens)
        # 解题
        response = text_response(request.system_message, question, request.math_max_new_tokens)
        # 返回结果
        return {"response": response}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 批量添加学生账号
@router.post("/add-student-in")
async def add_student_in(request: AddStudentInListRequest):
    try:
        result = add_in_list(DATABASE_URL, "Student", request.studentlist)
        if result:
            return {"status": "success", "message": "成功批量增加学生账号"}
        else:
            return {"status": "fail", "message": "批量增加失败，部分成员可能已加入"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")