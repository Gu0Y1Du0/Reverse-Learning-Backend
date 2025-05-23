from datetime import datetime
from typing import Union, Dict, List

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
import pandas as pd

from .config import DATABASE_URL
from .models import ConversationScore, Class, Student, Teacher

engine = create_engine(DATABASE_URL)

# 从MySQL数据库提取学习状态得分并转化为execl表
def export_studentname_to_excel(db_url, studentname, excel_file):
    try:
        # 创建数据库引擎和会话
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()

        # 查询指定username的行
        results = session.query(ConversationScore).filter_by(stundentrname=studentname).all()

        if not results:
            print(f"未找到与用户名 '{studentname}' 相关的数据。")
            return

        # 将查询结果转换为字典列表
        data = [
            {
                "ID": row.studentid,
                "用户名": row.studentname,
                "时间戳": row.timestamp,
                "问题深度": row.question_depth,
                "响应及时性": row.response_timeliness,
                "纠正主动性": row.correction_proactivity,
                "情感参与度": row.emotional_engagement,
                "总分": row.total_score,
            }
            for row in results
        ]

        # 转换为DataFrame
        df = pd.DataFrame(data)

        # 导出为Excel文件
        df.to_excel(excel_file, index=False, engine='openpyxl')

        print(f"成功将用户名 '{studentname}' 的数据导出到 {excel_file}")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        # 关闭会话
        session.close()

# 创建班级/拉学生进班级
def create_or_add_class(db_url: str, teacherid: int, student_identifier: Union[int, str], classname: str) -> bool:
    # student_identifier: 可以是学生的ID(int)或姓名(str)
    try:
        # 输入验证
        if not isinstance(teacherid, int) or teacherid <= 0:
            raise ValueError("教师ID必须为正整数")
        if not classname.strip():
            raise ValueError("班级名称不能为空")
        if not isinstance(student_identifier, (int, str)):
            raise TypeError("学生标识符必须是整数或字符串")
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)

        with Session() as session:  # 自动会话管理
            try:
                # 验证教师存在性
                teacher = session.query(Teacher).get(teacherid)
                if not teacher:
                    print(f"教师ID {teacherid} 不存在")
                    return False
                # 学生查询逻辑
                if isinstance(student_identifier, int):
                    student = session.query(Student).get(student_identifier)
                else:
                    student = session.query(Student).filter(Student.studentname == student_identifier).first()
                if not student:
                    print(f"学生不存在: {student_identifier}")
                    return False

                # 检查班级是否已存在
                existing_class = session.query(Class).filter(Class.teacherid == teacherid, Class.classname == classname).first()

                if existing_class:
                    print(f"班级 {classname} 已存在")
                    existing_student = session.query(Student).filter(Class.teacherid == teacherid, Class.classname == classname, Class.studentid == student.studentid).first()
                    if existing_student:
                        print("已实现，无需创建或添加")
                        return True
                    else:
                        # 创建班级记录
                        new_roll = Class(
                            teacherid=teacherid,
                            classname=classname,
                            studentid=student.studentid
                        )
                        session.add(new_roll)
                        session.commit()
                        print(f"教师 {teacher.teachername} 成功创建班级 {classname}")
                        print(f"关联学生: {student.studentname}(ID:{student.studentid})")
                        return True
                else:
                    # 创建班级记录
                    new_class = Class(
                        teacherid=teacherid,
                        classname=classname,
                        studentid=student.studentid
                    )
                    session.add(new_class)
                    session.commit()
                    print(f"教师 {teacher.teachername} 成功创建班级 {classname}")
                    print(f"关联学生: {student.studentname}(ID:{student.studentid})")
                    return True
            except Exception as inner_e:
                session.rollback()  # 回滚事务
                print(f"数据库操作失败: {inner_e}")
                return False
    except ValueError as ve:
        print(f"参数错误: {str(ve)}")
        return False
    except Exception as e:
        print(f"操作失败: {str(e)}")
        return False

# 解散班级
def dissolve_class(db_url: str, teacherid: int, classname: str) -> bool:
    try:
        # 输入验证
        if not isinstance(teacherid, int) or teacherid <= 0:
            raise ValueError("教师ID必须为正整数")
        if not classname.strip():
            raise ValueError("班级名称不能为空")

        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        with Session() as session:  # 使用上下文管理器自动处理会话
            try:
                # 精确查询：确保教师ID和班级名匹配
                deleted_count = session.query(Class).filter(Class.teacherid == teacherid, Class.classname == classname).delete()
                session.commit()
                if deleted_count > 0:
                    print(f"成功删除班级: {classname}，共{deleted_count} 名学生")
                    return True
                else:
                    print(print(f"未找到教师 {teacherid} 创建的班级 {classname}"))
                    return False
            except Exception as inner_e:
                session.rollback()  # 回滚事务
                print(f"数据库操作失败: {inner_e}")
                return False
    except ValueError as ve:
        print(f"参数错误: {ve}")
        return False
    except Exception as e:
        print(f"发生未知错误: {e}")
        return False

# 教师踢出成员
def delete_member_from_class(db_url: str, teacher_identifier: Union[int, str], student_identifier: Union[int, str], classname: str) -> bool:
    try:
        # 参数验证
        if not classname.strip():
            raise ValueError("班级名称不能为空")
        if not isinstance(teacher_identifier, (int, str)):
            raise TypeError("教师标识符类型错误")
        if not isinstance(student_identifier, (int, str)):
            raise TypeError("学生标识符类型错误")

        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        with Session() as session:
            with session.begin():
            # 验证教师权限
                if isinstance(teacher_identifier, int):
                    teacher = session.query(Teacher).get(teacher_identifier)
                else:
                    teacher = session.query(Teacher).filter(Teacher.teachername == teacher_identifier).first()
                if not teacher:
                    print("教师账号不存在")
                    return False

                # 查询目标班级
                target_class = session.query(Class).filter(Class.teacherid == teacher.teacherid, Class.classname == classname).first()
                if not target_class:
                    print(f"教师 {teacher.teachername} 未创建班级 {classname}")
                    return False
                # 查询要移除的学生
                if isinstance(student_identifier, int):
                    student = session.query(Student).get(student_identifier)
                else:
                    student = session.query(Student).filter(Student.studentname == student_identifier).first()
                if not student:
                    print("学生账号不存在")
                    return False
                # 执行删除操作
                result = session.query(Class).filter(Class.teacherid == teacher.teacherid, Class.classname == classname, Class.studentid == student.studentid).delete()
                if not result:
                    print("踢出失败")
                    return False
                else:
                    print(f"已从班级 {classname} 移除学生 {student.studentname}")
                    return True
    except ValueError as ve:
        print(f"参数错误: {str(ve)}")
        return False
    except Exception as e:
        print(f"操作失败: {str(e)}")
        return False

# 获取指定班级学生列表
def get_class_details(db_url: str, teacherid: int, classname: str) -> Dict[str, Union[str, List[str]]]:
    # Returns:
    # {
    #     "classname": str,
    #     "teacher": str,
    #     "students": [
    #         {"id": 1001, "name": "张三"},
    #         {"id": 1002, "name": "李四"}
    #     ]
    # }
    result_template = {
        "classname": classname,
        "teacher": "",
        "students": []
    }
    try:
        if not isinstance(teacherid, int) or teacherid <= 0:
            raise TypeError("教师ID必须为正整数")
        if not classname.strip():
            raise ValueError("班级名称不能为空")

        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)

        with (Session() as session):
            # 获取教师信息
            teacher = session.query(Teacher).get(teacherid)
            if not teacher:
                print(f"教师ID {teacherid} 不存在")
                return result_template
            result_template["teacher"] = teacher.teachername

            # 获取班级所有学生ID
            class_records = session.query(Class).filter(Class.teacherid == teacherid, Class.classname == classname, Class.studentid.isnot(None)) .all()

            # 提取有效学生ID
            student_ids = [cr.studentid for cr in class_records if cr.studentid]
            if not student_ids:
                return result_template

            # 批量获取学生详细信息
            students = session.query(Student.studentid, Student.studentname).filter(Student.studentid.in_(student_ids)).all()

            # 构造学生信息字典列表
            result_template["students"] = [{"id": s.studentid, "name": s.studentname}for s in students]
            return result_template

    except ValueError as ve:
        print(f"参数错误: {str(ve)}")
        return result_template
    except Exception as e:
        print(f"查询失败: {str(e)}")
        return result_template

# 获取学生提问频率
def get_frequency(db_url: str, student_identifier: Union[int, str], starttime: datetime, endtime: datetime) -> Dict[str, Union[str, int]]:
    # Return:
    # {
    #     "studentid": int,
    #     "studentname": str,
    #     "frequency": int
    # }
    result = {
        "studentid": 0,
        "studentname": "",
        "frequency": 0
    }
    try:
        # 参数验证
        if not isinstance(student_identifier, (int, str)):
            raise ValueError("学生标识符必须是整数或字符串")
        if starttime > endtime:
            raise ValueError("起始时间不能晚于结束时间")

        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            if isinstance(student_identifier, int):
                student = session.query(Student).get(student_identifier)
            else:
                student = session.query(Student).filter(Student.studentname == student_identifier).first()
            if not student:
                raise ValueError("学生账号不存在")
            frequency = session.query(ConversationScore).filter(ConversationScore.studentname == student.studentname, ConversationScore.timestamp >= starttime, ConversationScore.timestamp <= endtime).count()
            # 构建结果
            result.update({
                "studentid": student.studentid,
                "studentname": student.studentname,
                "frequency": frequency
            })
            return result

    except SQLAlchemyError as e:
        session.rollback()
        raise

# 获取学生名
def get_studentname(db_url: str, student_identifier: Union[int, str]) -> str:
    try:
        # 参数验证
        if not isinstance(student_identifier, (int, str)):
            raise ValueError("学生标识符必须是整数或字符串")

        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            if isinstance(student_identifier, int):
                student = session.query(Student).get(student_identifier)
            else:
                student = session.query(Student).filter(Student.studentname == student_identifier).first()
            if not student:
                raise ValueError("学生账号不存在")

        return student.studentname
    except SQLAlchemyError as e:
        raise RuntimeError(f"数据库查询失败: {str(e)}") from e

# 获取教师名
def get_teachername(db_url: str, teacher_identifier: Union[int, str]) -> str:
    try:
        # 参数验证
        if not isinstance(teacher_identifier, (int, str)):
            raise ValueError("教师标识符必须是整数或字符串")

        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            if isinstance(teacher_identifier, int):
                teacher = session.query(Teacher).get(teacher_identifier)
            else:
                teacher = session.query(Teacher).filter(Teacher.teachername == teacher_identifier).first()
            if not teacher:
                raise ValueError("教师账号不存在")

        return teacher.teachername
    except SQLAlchemyError as e:
        raise RuntimeError(f"数据库查询失败: {str(e)}") from e

# 学生主动加入班级
def join_class(db_url: str, teacher_identifier: Union[int, str], student_identifier: Union[int, str], classname: str) -> bool:
    try:
        # 参数验证
        if not classname.strip():
            raise ValueError("班级名称不能为空")
        if not isinstance(teacher_identifier, (int, str)):
            raise TypeError("教师标识符类型错误")
        if not isinstance(student_identifier, (int, str)):
            raise TypeError("学生标识符类型错误")

        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        with Session() as session:
            try:
                # 验证教师权限
                if isinstance(teacher_identifier, int):
                    teacher = session.query(Teacher).get(teacher_identifier)
                else:
                    teacher = session.query(Teacher).filter(Teacher.teachername == teacher_identifier).first()
                if not teacher:
                    print("教师账号不存在")
                    return False

                # 查询目标班级
                target_class = session.query(Class).filter(Class.teacherid == teacher.teacherid,
                                                           Class.classname == classname).first()
                if not target_class:
                    print(f"教师 {teacher.teachername} 未创建班级 {classname}")
                    return False
                # 查询要加入的学生
                if isinstance(student_identifier, int):
                    student = session.query(Student).get(student_identifier)
                else:
                    student = session.query(Student).filter(Student.studentname == student_identifier).first()
                if not student:
                    print("学生账号不存在")
                    return False
                # 执行加入操作
                # 检查学生是否已加入
                existing_student = session.query(Class).filter(Class.teacherid == teacher.teacherid, Class.classname == classname, Student.studentid == student.studentid).first()

                if existing_student:
                    print(f"班级 {classname} 已存在")
                    return True
                else:
                    # 创建班级记录
                    new_class = Class(
                        teacherid=teacher.teacherid,
                        classname=classname,
                        studentid=student.studentid
                    )
                    session.add(new_class)
                    session.commit()
                    print(f"学生: {student.studentname}(ID:{student.studentid})")
                    print(f"加入 {teacher.teachername} 的 {classname} 成功")
                    return True
            except Exception as inner_e:
                session.rollback()  # 回滚事务
                print(f"数据库操作失败: {inner_e}")

    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        session.close()

# 批量导入
def add_in_list(db_url: str, table_name: str, list: List) -> bool:
    try:
        if table_name != 'Student' and table_name != 'Teacher':
            raise ValueError("不正确传入")

        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        with Session() as session:
            try:
                if table_name == 'Student':
                    for student in list:
                        # 加密密码
                        salt = bcrypt.gensalt()
                        hashed_password = bcrypt.hashpw(student.password.encode('utf-8'), salt).decode('utf-8')
                        new_student = Student(
                            studentname=student.studentname,
                            password_hash=hashed_password
                        )
                        session.add(new_student)
                        session.commit()
                else:
                    for teacher in list:
                        # 加密密码
                        salt = bcrypt.gensalt()
                        hashed_password = bcrypt.hashpw(teacher.password.encode('utf-8'), salt).decode('utf-8')
                        new_teacher = Teacher(
                            teachername=teacher.teachername,
                            password_hash=hashed_password
                        )
                        session.add(new_teacher)
                        session.commit()
                return True
            except Exception as inner_e:
                session.rollback()  # 回滚事务
                print(f"数据库操作失败: {inner_e}")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        session.close()

def add_student_to_class_in_list(db_url: str, teacher_identifier: Union[int, str], classname: str, list: List) -> bool:
    try:
        # 参数验证
        if not classname.strip():
            raise ValueError("班级名称不能为空")
        if not isinstance(teacher_identifier, (int, str)):
            raise TypeError("教师标识符类型错误")

        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        with Session() as session:
            try:
                # 验证教师权限
                if isinstance(teacher_identifier, int):
                    teacher = session.query(Teacher).get(teacher_identifier)
                else:
                    teacher = session.query(Teacher).filter(Teacher.teachername == teacher_identifier).first()
                if not teacher:
                    print("教师账号不存在")
                    return False

                for id in list:
                    # 创建班级记录
                    new_class = Class(
                        teacherid=teacher.teacherid,
                        classname=classname,
                        studentid=id
                    )
                    session.add(new_class)
                    session.commit()
                return True
            except Exception as inner_e:
                session.rollback()  # 回滚事务
                print(f"数据库操作失败: {inner_e}")
    except Exception as e:
        print(f"发生错误: {e}")
        return False
    finally:
        session.close()