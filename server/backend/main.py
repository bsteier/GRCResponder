from fastapi import FastAPI, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from typing import List
import uuid
from datetime import datetime
from models import Conversation, Message, SessionLocal
from schemas import ConversationCreate, MessageCreate, ConversationResponse, MessageResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from models import Base, engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Creating tables")
    Base.metadata.create_all(bind=engine)
    print("Tables created (or already exist)")
    yield
    print("App shutdown")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Post a conversation
@app.post("/conversations", response_model=ConversationResponse)
def create_conversation(conversation: ConversationCreate, db: Session = Depends(get_db)):
    conversation_id = str(uuid.uuid4()) 
    db_conversation = Conversation(
        id=conversation_id,
        user_id=conversation.user_id,
        title=conversation.title,
        timestamp=conversation.timestamp
    )
    db.add(db_conversation)
    db.commit()
    db.refresh(db_conversation)
    return db_conversation


# Post a message to a conversation
@app.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
def add_message(conversation_id: str, message: MessageCreate, db: Session = Depends(get_db)):
    db_conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not db_conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    message_id = str(uuid.uuid4())
    db_message = Message(
        id=message_id,
        conversation_id=conversation_id,
        sender=message.sender,
        message=message.message,
        timestamp=message.timestamp,
        files=message.files
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message

# Get conversations
@app.get("/conversations", response_model=List[ConversationResponse])
def get_user_conversations(user_id: str, db: Session = Depends(get_db)):
    conversations = db.query(Conversation).filter(Conversation.user_id == user_id).all()
    return conversations

# Get messages for a conversation
@app.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
def get_conversation_messages(conversation_id: str, db: Session = Depends(get_db)):
    messages = db.query(Message).filter(Message.conversation_id == conversation_id).all()
    return messages

