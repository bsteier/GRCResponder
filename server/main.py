from fastapi import FastAPI, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from typing import List
import uuid
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from models import Conversation, Message, SessionLocal
from schemas import ConversationCreate, MessageCreate, ConversationResponse, MessageResponse
from rag_pipeline import graph 

app = FastAPI()
# Allow all origins for development purposes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can specify allowed origins here
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods like GET, POST, etc.
    allow_headers=["*"],  # Allows all headers
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
    conversation_id = str(uuid.uuid4())  # Generate unique ID for the conversation
    db_conversation = Conversation(
        id=conversation_id,
        user_id=conversation.user_id,
        title=conversation.title,
        timestamp=conversation.timestamp
    )
    
    try:
        db.add(db_conversation)  # Add the conversation to the session
        db.commit()  # Commit the transaction
        db.refresh(db_conversation)  # Refresh the object to get the updated data (if any)
        return db_conversation  # Return the created conversation
    except Exception as e:
        db.rollback()  # Rollback the transaction in case of error
        raise HTTPException(status_code=500, detail=f"Error creating conversation: {str(e)}")

# Post a message to a conversation and llm
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
        timestamp=message.timestamp
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)

    # Run graph 
    result = graph.invoke({"messages": [message]})
    ai_response = None

    # Save response
    for msg in reversed(result["messages"]):
        print(msg)

        if msg.sender == 'ai':
            ai_msg = Message(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                sender="ai",
                message=ai_response.content,
                timestamp=msg.timestamp,  # Use current time for response
            )
            db.add(ai_msg)
            db.commit()
            return {"response": ai_response.content}
    raise HTTPException(status_code=500, detail="No AI response generated.")


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

