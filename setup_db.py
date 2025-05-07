from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship, sessionmaker, scoped_session, declarative_base
from datetime import datetime

engine = create_engine('sqlite:///messages.db')
db_session = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    joined_date = Column(DateTime, default=datetime.utcnow)
    messages = relationship('Messages', backref='user', lazy='select', cascade="all, delete-orphan")

class Messages(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    severity = Column(String, nullable=False)  # New column for severity

Base.metadata.create_all(bind=engine)