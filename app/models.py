from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
import uuid

Base = declarative_base()

class Room(Base):
    """
    Core Room model representing a temp chat space
    Each room has a unique shareable id and expires after 24 hours
    """
    __tablename__ = "rooms"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    topic = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(hours=24))
    max_participants = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)

    # Relationships
    posts = relationship("Post", back_populates="room", cascade="all, delete-orphan")
    participants = relationship("Participant", back_populates="room", cascade="all, delete-orphan")

    @property
    def is_expired(self):
        # Check if the room has expired
        return datetime.utcnow() > self.expires_at

    @property
    def time_remaining(self):
        # Get remaining time in seconds
        if self.is_expired:
            return 0
        return int((self.expires_at - datetime.utcnow()).total_seconds())
    

class Post(Base):
    """
    Individual posts within a room
    Supports threading - posts can reply to other posts
    """
    __tablename__ = "posts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String, ForeignKey('rooms.id', ondelete="CASCADE"))
    content = Column(Text, nullable=False)
    anonymous_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Threading support - posts can reply to other posts
    parent_id = Column(String, ForeignKey("posts.id", ondelete="CASCADE"), nullable=True)

    # Vote tracking
    vote_score = Column(Integer, default=0)

    # Relationships
    room = relationship("Room", back_populates="posts")
    parent = relationship("Post", remote_side=[id], backref="replies")
    votes = relationship("Vote", back_populates="post", cascade="all, delete-orphan")


class Participant(Base):
    """
    Track anonymous participants in each room
    Used for generating consistent anonymous IDs and managing room capacity
    """
    __tablename__ = "participants"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String, ForeignKey("rooms.id", ondelete="CASCADE"))
    session_id = Column(String, nullable=False)  # Browser session identifier
    anonymous_id = Column(String, nullable=False)  # Generated anonymous name
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    room = relationship("Room", back_populates="participants")


class Vote(Base):
    """
    Community voting system for post quality
    Participants can upvote/downvote posts for relevance
    """
    __tablename__ = "votes"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    post_id = Column(String, ForeignKey("posts.id", ondelete="CASCADE"))
    session_id = Column(String, nullable=False)  # Who voted
    vote_type = Column(String, nullable=False)  # 'up' or 'down'
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    post = relationship("Post", back_populates="votes")