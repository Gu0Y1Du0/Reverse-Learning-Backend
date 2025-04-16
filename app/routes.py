import base64
import re
import bcrypt
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException, File, UploadFile, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func
from starlette.responses import RedirectResponse, FileResponse
from sqlalchemy.orm import sessionmaker
from .config import ENVPATH, DATABASE_URL
from .services import call_qwen, call_qwen_vl, call_deepseek_r1_distill
from .models import User, ConversationScore
from .database import engine, export_username_to_excel
from .utils import mkdir, encode_image, extract_json_content

router = APIRouter()

# 创建会话工厂
SessionLocal = sessionmaker(bind=engine)

# 登录请求模型
class LoginRequest(BaseModel):
    username: str
    password: str

# 注册请求模型
class RegisterRequest(BaseModel):
    username: str
    password: str

# 多轮对话请求模型
class ChatRequest(BaseModel):
    username: str  # 用户名，用于区分用户会话
    prompt: str    # 用户输入的问题

class ViewRequest(BaseModel):
    username: str
    file: str   # 图片的Base64格式

# 学习建议模型
class AdviceRequest(BaseModel):
    username: str
    prompt: str

# 资源下载模型
class GetsourceRequest(BaseModel):
    username: str
    sourcenumber: int

# 存储用户对话历史（简单实现，使用内存中的字典）
conversation_history = {}

# 创建文件路径
filepath = ENVPATH

# 登录
@router.post("/login")
async def login(request: LoginRequest):
    try:
        print(f"Received request: {request}")
        db = SessionLocal()
        # 查询用户
        user = db.query(User).filter(User.username == request.username).first()
        if not user:
            raise HTTPException(status_code=401, detail="用户名不存在")
        # 验证密码
        if not bcrypt.checkpw(request.password.encode('utf-8'), user.password_hash.encode('utf-8')):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
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
        return {"status": "success", "message": "登录成功"}
    except Exception as e:
        print(f"Error during login: {str(e)}")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后再试")

# 注册
@router.post("/register")
async def register(request: RegisterRequest):
    print(f"Received request: {request}")
    db = SessionLocal()
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在，请选择其他用户名")
    # 加密密码
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(request.password.encode('utf-8'), salt).decode('utf-8')
    # 创建新用户
    new_user = User(
        username=request.username,
        password_hash = hashed_password
    )
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"status": "success", "message": "注册成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

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
            "计算学习状态分数规则如下(均为10分制)："
            "学习深度(分数占比30％)：基于问题链长度（平均值）。"
            "响应及时性(分数占比20％)：基于AI的平均响应时间。"
            "自我修正主动性(分数占比25％)：基于用户对错误的自我修正次数。"
            "情感参与度(分数占比25％)：基于用户对话中的情感词汇密度。"
        )
        # 获取用户印记 建立数据库连接
        username = request.username
        prompt = request.prompt
        db = SessionLocal()
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
                    username=username,
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
@router.get("/evaluation/{username}")
async def get_evaluation(username: str):
    # 从数据库获取用户的最新评估数据
    try:
        db = SessionLocal()
        latest_score = (
            db.query(ConversationScore)
            .filter(ConversationScore.username == username)
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
        username = request.username
        if not request.username:
            raise HTTPException(status_code=400, detail="Username is required.")
        file = request.file
        # 检查文件类型是否为图片
        if not file.startswith("data:image/"):
            return JSONResponse(status_code=400, content={"message": "只支持图片文件！"})
        prompt = (
            "请按照以下 JSON 格式返回结果，不要使用markdown格式："
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
                user_problem_txt_path = user_folder / f"{username}_problem_txt.txt"
                with open(user_problem_txt_path, "a", encoding="utf-8") as f:
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

# 学习建议
@router.post("/advice")
async def deepseekadvice(request: AdviceRequest):
    try:
        # 定义 Preprompt
        Preprompt = (
            "根据用户画像，给出用户学习建议。"
            "格式以二级标题'学习建议开头'，正文部分写学习建议。"
        )
        # 获取用户印记
        username = request.username
        prompt = request.prompt
        # 创建用户文件夹和用户画像文件路径
        user_folder = Path(ENVPATH) / username
        mkdir(user_folder)
        user_profile_path = user_folder / f"{username}_profile.txt"
        print(f"用户画像文件路径: {user_profile_path}")
        # 加载用户画像
        if not user_profile_path.exists():
            raise HTTPException(status_code=400, detail="您还没开始使用逆向学习问答助手！")
        with open(user_profile_path, "r", encoding="utf-8") as f:
            user_profile = f.read().strip()  # 去除可能的空白字符
        # 如果用户画像为空，也返回错误
        if not user_profile:
            raise HTTPException(status_code=400, detail="您还没开始使用逆向学习问答助手！")

        # 调用AI时，将Preprompt，用户画像拼接到用户输入
        full_prompt_for_ai = f"{Preprompt}\n\n用户画像：\n{user_profile}\n\n用户输入内容:\n{prompt}"
        response_text = call_deepseek_r1_distill(full_prompt_for_ai)
        # 写入文件（仅保存用户原始输入和 AI 回复）
        date_str = datetime.now().strftime("%Y-%m-%d")
        file_path = user_folder / f"{username}_advice.txt"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"在{date_str}\n\n{username}获取学习建议：\n\n{response_text}\n\n")
        return {"status": "success", "response": response_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

# 资源下载
@router.post("/source")
async def get_source(request: GetsourceRequest):
    username = request.username
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
                file_path = user_folder / f"{username}_problem_txt.txt"
                filename = f"{username}_problem_txt.txt"
                return FileResponse(file_path, media_type="application/octet-stream", filename=filename)
            # 学习建议
            case 3:
                file_path = user_folder / f"{username}_advice.txt"
                filename = f"{username}_advice.txt"
                return FileResponse(file_path, media_type="application/octet-stream", filename=filename)
            # 导出学习状态分数记录execl表
            case 4:
                file_path = user_folder / f"{username}_conversation_scores.xlsx"
                filename = f"{username}_conversation_scores.xlsx"
                export_username_to_excel(DATABASE_URL, username, file_path)
                return FileResponse(file_path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=filename)
    except Exception as e:
        raise  HTTPException(status_code=500, detail=f"资源下载报错: {str(e)}")

# 从 MySQL 数据库获取询问次数和时间
@router.post("/recentlyask/{username}")
async def recentlyAsk(username: str):
    try:
        db = SessionLocal()
        # 获取当前日期，不包含时间部分
        current_date = datetime.utcnow().date()
        # 计算七天前的日期
        seven_days_ago = current_date - timedelta(days=7)
        # 查询选定用户在最近七天内的插入记录
        result = (
            db.query(
                func.date(ConversationScore.timestamp).label("date"),  # 按日期分组
                func.count(ConversationScore.id).label("count")  # 统计每天的插入次数
            )
            .filter(
                ConversationScore.username == username,  # 筛选用户名
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
        return {"username": username, "recent_stats": stats}
    except Exception as e:
        raise  HTTPException(status_code=500, detail=f"获取提问次数和日期出错: {str(e)}")

# 调试显示
@router.get("/")
async def redirect_to_docs():
    return RedirectResponse(url="/docs")