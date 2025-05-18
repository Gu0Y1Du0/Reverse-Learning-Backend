from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, Float, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Student(Base):
    __tablename__ = "student"
    studentid = Column(Integer, primary_key=True)
    studentname = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String(60), nullable=False)

class Teacher(Base):
    __tablename__ = "teacher"
    teacherid = Column(Integer, primary_key=True)
    teachername = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String(60), nullable=False)

class Class(Base):
    __tablename__ = "class"
    id = Column(Integer, primary_key=True, autoincrement=True)
    teacherid = Column(Integer, nullable=True)
    classname = Column(String(255), nullable=False)
    studentid = Column(Integer, nullable=True)

class AdministratorMechanism(Base):
    __tablename__ = "administrator_mechanism"
    AdministratorInstitution = Column(String(255), primary_key=True)
    InvitationCode = Column(String(50), nullable=True)

class ConversationScore(Base):
    __tablename__ = "conversation_scores"
    id = Column(Integer, primary_key=True, autoincrement=True)
    studentname = Column(String(50), nullable=False)
    timestamp = Column(Date, default=datetime.now())
    question_depth = Column(Float, nullable=False)
    response_timeliness = Column(Float, nullable=False)
    correction_proactivity = Column(Float, nullable=False)
    emotional_engagement = Column(Float, nullable=False)
    total_score = Column(Float, nullable=False)
