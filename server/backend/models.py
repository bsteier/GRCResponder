from sqlalchemy import create_engine, Column, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from dotenv import load_dotenv
import os



# temp
POSTGRES_URL = "postgresql+psycopg2://postgres:password@localhost:5432/grc"
print("Using DB URL:", POSTGRES_URL)

engine = create_engine(POSTGRES_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Conversation model
class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True) 
    title = Column(String, default="New Conversation")
    timestamp = Column(DateTime)

    # Relationship to messages
    messages = relationship("Message", back_populates="conversation")

# Message model
class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True, index=True) 
    conversation_id = Column(String, ForeignKey("conversations.id"))
    sender = Column(String)
    message = Column(Text)
    timestamp = Column(DateTime)
    files = Column(Text, nullable=True) 

    # Relationship to conversation
    conversation = relationship("Conversation", back_populates="messages")
