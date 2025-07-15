from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models import Room, Post, Participant, Vote
from app.schemas import RoomCreate, PostCreate, VoteCreate
from datetime import datetime, timedelta
import hashlib
import random

# Anonymous identity generation
ADJECTIVES = ["Happy", "Calm", "Bright", "Swift", "Gentle", "Bold", "Quiet", "Clever", "Kind", "Brave"]
ANIMALS = ["Cat", "Dog", "Bird", "Fish", "Bear", "Wolf", "Fox", "Deer", "Owl", "Bee"]

def generate_anonymous_id(roon_id: str, session_id: str) -> str:
    """
    Generate consistent anonymous identity for a user in a specific room
    Same Session_id + room_id always produces the same anonymous_id
    """

    # create hash from room_id and session_id
    hash_input = f"{roon_id}-{session_id}"
    hash_digest = hashlib.md5(hash_input.encode()).hexdigest()

    # Use hash to deterministically select adjective and animal
    adj_index = int(hash_digest[:2], 16) % len(ADJECTIVES)
    animal_index = int(hash_digest[2:4], 16) % len(ANIMALS)

    return f"{ADJECTIVES[adj_index]} {ANIMALS[animal_index]}"

# Room CRUD Operations
def create_room(db: Session, room_data: RoomCreate) -> Room:
    """Create a new room with expiration time"""
    expires_at = datetime.utcnow() + timedelta(hours=room_data.duration_hours)

    room = Room(
        topic=room_data.topic,
        expires_at=expires_at,
        max_participants=room_data.max_participants
    )

    db.add(room)
    db.commit()
    db.refresh(room)
    return room

def get_room(db: Session, room_id: str) -> Room:
    """Get room by ID, return None if expireed or doesn't exist"""
    room = db.query(Room).filter(Room.id == room_id).first()

    if not room or room.is_expired:
        return None
    
    return room

def get_room_with_posts(db: Session, room_id: str) -> Room:
    """Get room with all posts and replies"""
    room = get_room(db, room_id)
    if not room:
        return None
    
    # Get all posts for this room, ordered by creation time
    posts = db.query(Post).filter(Post.room_id == room_id).order_by(Post.created_at).all()
    room.threaded_posts = []

    for post in posts:
        if post.parent_id is None: # Top-level posts
            post.replies = [p for p in posts if p.parent_id == post.id]
            room.threaded_posts.append(post)

    return room

def delete_expired_rooms(db: Session) -> int:
    """Delete all expired rooms and their related data"""
    expired_rooms = db.query(Room).filter(Room.expires_at < datetime.utcnow()).all()

    count = len(expired_rooms)
    for room in expired_rooms:
        db.delete(room)

    db.commit()
    return count

# Participant CRUD operations
def join_room(db: Session, room_id: str, session_id: str) -> Participant:
    """Add participant to room or update existing participant"""
    room = get_room(db, room_id)
    if not room:
        return None
    
    # Check if participant already exists
    participant = db.query(Participant).filter(
        and_(Participant.room_id == room_id, Participant.session_id == session_id)
    ).first()
    
    if participant:
        # Update last seen
        participant.last_seen = datetime.utcnow()
        db.commit()
        return participant
    
    # Check room capacity
    current_participants = db.query(Participant).filter(Participant.room_id == room_id).count()
    if current_participants >= room.max_participants:
        return None
    
    # Create new participant
    anonymous_id = generate_anonymous_id(room_id, session_id)
    participant = Participant(
        room_id=room_id,
        session_id=session_id,
        anonymous_id=anonymous_id
    )
    
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


def get_participant(db: Session, room_id: str, session_id: str) -> Participant:
    """Get participant by room and session"""
    return db.query(Participant).filter(
        and_(Participant.room_id == room_id, Participant.session_id == session_id)
    ).first()

def get_room_participant_count(db: Session, room_id: str) -> int:
    """Get count of participants in room"""
    return db.query(Participant).filter(Participant.room_id == room_id).count()

# Post CRUD operations
def create_post(db: Session, room_id: str, session_id: str, post_data: PostCreate) -> Post:
    """Create a new post in a room"""
    participant = get_participant(db, room_id, session_id)
    if not participant:
        return None
    
    # Validate parent post exists if specified
    if post_data.parent_id:
        parent_post = db.query(Post).filter(
            and_(Post.id == post_data.parent_id, Post.room_id == room_id)
        ).first()
        if not parent_post:
            return None
    
    post = Post(
        room_id=room_id,
        content=post_data.content,
        anonymous_id=participant.anonymous_id,
        parent_id=post_data.parent_id
    )
    
    db.add(post)
    db.commit()
    db.refresh(post)
    return post

def get_post(db: Session, post_id: str) -> Post:
    """Get post by ID"""
    return db.query(Post).filter(Post.id == post_id).first()

# Vote CRUD operations
def vote_on_post(db: Session, post_id: str, session_id: str, vote_data: VoteCreate) -> Vote:
    """Vote on a post (up/down)"""
    post = get_post(db, post_id)
    if not post:
        return None
    
    # Check if user already voted on this post
    existing_vote = db.query(Vote).filter(
        and_(Vote.post_id == post_id, Vote.session_id == session_id)
    ).first()
    
    if existing_vote:
        # Update existing vote
        old_vote_type = existing_vote.vote_type
        existing_vote.vote_type = vote_data.vote_type
        
        # Update post score
        if old_vote_type == 'up' and vote_data.vote_type == 'down':
            post.vote_score -= 2
        elif old_vote_type == 'down' and vote_data.vote_type == 'up':
            post.vote_score += 2
        
        db.commit()
        return existing_vote
    
    # Create new vote
    vote = Vote(
        post_id=post_id,
        session_id=session_id,
        vote_type=vote_data.vote_type
    )
    
    # Update post score
    if vote_data.vote_type == 'up':
        post.vote_score += 1
    else:
        post.vote_score -= 1
    
    db.add(vote)
    db.commit()
    db.refresh(vote)
    return vote
