from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# Room Schemas
class RoomCreate(BaseModel):
    """Schema for creating a new room"""
    topic: Optional[str] = Field(None, max_length=200)
    duration_hours: Optional[int] = Field(24, ge=1, le=168) # an hour to one week
    max_participants: Optional[int] = Field(100, ge=1, le=1000)

class RoomResponse(BaseModel):
    """Schema for room information response"""
    id: str
    topic: Optional[str]
    created_at: datetime
    expires_at: datetime
    max_participants: int
    is_active: bool
    time_remaining: int
    participant_count: int

    class Config:
        from_attributes = True


# Post Schemas
class PostCreate(BaseModel):
    """Schema for creating a new post"""
    content: str = Field(..., min_length=1, max_length=500)
    parent_id: Optional[str] = None # For threading replies

class PostResponse(BaseModel):
    """Schema for post information required"""
    id: str
    content: str
    anonymous_id: str
    created_at: datetime
    parent_id: Optional[str]
    vote_score: int
    replies: List['PostResponse'] = []

# Update forward reference
PostResponse.model_rebuild()

# Vote Schemas
class VoteCreate(BaseModel):
    """Schema for voting on posts"""
    vote_type: str = Field(..., regex="^(up|down)$")

class VoteResponse(BaseModel):
    """Schema for vote response"""
    post_id: str
    vote_type: str
    new_score: int

# WebSocket Message Schemas
class WebSocketMessage(BaseModel):
    """Schema for websocket messages"""
    type: str # 'new_post', 'new_vote', 'user_joined', 'user_left', 'room_expiring'
    data: dict

# Anonymous Identity Schema
class AnonymousIdentity(BaseModel):
    """Schema for anonymous user identity"""
    session_id: str
    anonymous_id: str
    room_id: str