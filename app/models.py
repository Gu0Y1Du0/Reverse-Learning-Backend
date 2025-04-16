from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, Float
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    userid = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String(60), nullable=False)

class ConversationScore(Base):
    __tablename__ = "conversation_scores"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False)
    timestamp = Column(Date, default=datetime.utcnow)
    question_depth = Column(Float, nullable=False)
    response_timeliness = Column(Float, nullable=False)
    correction_proactivity = Column(Float, nullable=False)
    emotional_engagement = Column(Float, nullable=False)
    total_score = Column(Float, nullable=False)
