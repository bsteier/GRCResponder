from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# add a conversation to db
class ConversationCreate(BaseModel):
    user_id: str
    title: Optional[str] = "New Conversation"
    timestamp: datetime

# add a message to db
class MessageCreate(BaseModel):
    sender: str 
    message: str
    timestamp: datetime

# retrieve a conversation
class ConversationResponse(BaseModel):
    id: str
    user_id: str
    title: str
    timestamp: datetime

# retrieve a message
class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender: str
    message: str
    timestamp: datetime

# Updating Title Model
class TitleUpdate(BaseModel):
    new_title: str
    