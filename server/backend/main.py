from fastapi import FastAPI, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from typing import List
import uuid
from datetime import datetime, timezone
from fastapi.middleware.cors import CORSMiddleware
from models import Conversation, Message, SessionLocal
from schemas import ConversationCreate, MessageCreate, ConversationResponse, MessageResponse, TitleUpdate
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from llm import getAIResponse
import logging

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

    ai_msg = processUserQuery(message.message, conversation_id, db)

    db.add(ai_msg)
    db.commit()
    db.refresh(db_message) 
    return JSONResponse(content={
        "response": "Message saved successfully",
        "data": {
            "message": ai_msg.message
        }
    }, status_code=200)


    # Run graph == This is the only connection to the AI that there should be
    # It just passed the query to the AI and should receive a response
    # response = getAIResponse(message.message)
    # print("AI Response:", response)
    # # Save response
    # if response and response["role"] == "ai":
    #     ai_msg = Message(
    #         id=str(uuid.uuid4()),
    #         conversation_id=conversation_id,
    #         sender="ai",
    #         message=response["content"],
    #         # I am not sure what this needs to be set to, but I am just getting
    #         # current time, FIX IF NOT CORRECT, IT is defaulting to UTC time
    #         # because I am trying to mimic the typescript Date.toISOString() method
    #         timestamp= datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),  # Use current time for response
    #     )
    #     db.add(ai_msg)
    #     db.commit()
    #     return ai_msg
    # raise HTTPException(status_code=500, detail="No AI response generated.")


# ====== Function that will take the query from the user and return the AI response ======
def processUserQuery(query: str, conversation_id: str, db: Session = Depends(get_db)) -> Message:
    # Run graph == This is the only connection to the AI that there should be
    # It just passed the query to the AI and should receive a response
    try:
        response = getAIResponse(query)

        # Just using this for now to show that AI gets a response
        print("AI Response:", response)
        
        # Save response
        ai_msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            sender="ai",
            message=response["content"],
            # I am not sure what this needs to be set to, but I am just getting
            # current time, FIX IF NOT CORRECT, IT is defaulting to UTC time
            # because I am trying to mimic the typescript Date.toISOString() method
            timestamp= datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        )  # Use current time for response

        # add the message to the DB
        # add_message(conversation_id, ai_msg, db)
        return ai_msg
    except Exception as e:
        logging.error(f"Error processing user query: {str(e)}")
        # Return error message as AI response
        error_msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            sender="ai",
            message="I apologize, but I encountered an error processing your request. Please try again.",
            timestamp=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        )
        return error_msg




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

# Delete conversation
@app.delete("/conversations/{conversation_id}", response_model=dict)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    convo = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    db.delete(convo)
    db.commit()

    return {"detail": "Conversation deleted"}

# Update conversation Name
@app.put("/conversations/{conversation_id}", response_model=dict)
def update_conversation_name(conversation_id: str, payload: TitleUpdate, db: Session = Depends(get_db)):
    convo = db.query(Conversation).filter(Conversation.id == conversation_id).first()

    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    old_title = convo.title
    convo.title = payload.new_title
    db.commit()

    return {"detail": f"Old title '{old_title}' changed to {payload.new_title}"}