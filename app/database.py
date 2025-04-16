from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import DATABASE_URL
from .models import ConversationScore
import pandas as pd

# 创建数据库引擎
engine = create_engine(DATABASE_URL, echo=True)

# 创建会话工厂
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 从MySQL数据库提取学习状态得分并转化为execl表
def export_username_to_excel(db_url, username, excel_file):
    try:
        # 创建数据库引擎和会话
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()

        # 查询指定username的行
        results = session.query(ConversationScore).filter_by(username=username).all()

        if not results:
            print(f"未找到与用户名 '{username}' 相关的数据。")
            return

        # 将查询结果转换为字典列表
        data = [
            {
                "ID": row.id,
                "用户名": row.username,
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

        print(f"成功将用户名 '{username}' 的数据导出到 {excel_file}")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        # 关闭会话
        session.close()
