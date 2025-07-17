from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
import asyncio
import logging

# Local imports
from app.database import get_db, create_tables
from app.schemas import *
from app.crud import *
from app.auth import *
from app.websocket import connection_manager, handle_websocket_connection, broadcast_new_post, broadcast_new_vote

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Ripple API",
    description="Anonymous, ephemeral social media platform",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database and start background tasks"""
    create_tables()
    
    # Start cleanup task for expired rooms
    asyncio.create_task(cleanup_expired_rooms_task())
    
    logger.info("Ripple API started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Ripple API shutting down")

# Background task to clean up expired rooms
async def cleanup_expired_rooms_task():
    """Background task that runs every 5 minutes to clean up expired rooms"""
    while True:
        try:
            # Get database session
            db = next(get_db())
            
            # Delete expired rooms
            deleted_count = delete_expired_rooms(db)
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired rooms")
            
            # Close database session
            db.close()
            
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
        
        # Wait 5 minutes before next cleanup
        await asyncio.sleep(300)

# Root endpoint
@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Ripple API is running",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

# Room endpoints
@app.post("/api/rooms", response_model=dict)
async def create_room_endpoint(
    room_data: RoomCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Create a new room
    Returns room info and session token for the creator
    """
    try:
        # Create room
        room = create_room(db, room_data)
        
        # Generate session ID for creator
        session_id = generate_session_id()
        
        # Create session token
        token = create_session_token(session_id, room.id)
        
        # Set session cookie
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax"
        )
        
        return {
            "room": RoomResponse(
                id=room.id,
                topic=room.topic,
                created_at=room.created_at,
                expires_at=room.expires_at,
                max_participants=room.max_participants,
                is_active=room.is_active,
                time_remaining=room.time_remaining,
                participant_count=0
            ),
            "session_token": token,
            "session_id": session_id
        }
    
    except Exception as e:
        logger.error(f"Error creating room: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create room"
        )

@app.get("/api/rooms/{room_id}", response_model=RoomResponse)
async def get_room_endpoint(
    room_id: str,
    db: Session = Depends(get_db)
):
    """Get room information"""
    room = get_room(db, room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found or expired"
        )
    
    participant_count = get_room_participant_count(db, room_id)
    
    return RoomResponse(
        id=room.id,
        topic=room.topic,
        created_at=room.created_at,
        expires_at=room.expires_at,
        max_participants=room.max_participants,
        is_active=room.is_active,
        time_remaining=room.time_remaining,
        participant_count=participant_count
    )

@app.post("/api/rooms/{room_id}/join", response_model=dict)
async def join_room_endpoint(
    room_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Join a room
    Returns session token and anonymous identity
    """
    # Get or generate session ID
    session_id = get_session_from_request(request)
    
    # Join room
    participant = join_room(db, room_id, session_id)
    
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot join room (full, expired, or doesn't exist)"
        )
    
    # Create session token
    token = create_session_token(session_id, room_id)
    
    # Set session cookie
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=False,  # Set to True in production
        samesite="lax"
    )
    
    return {
        "session_token": token,
        "anonymous_id": participant.anonymous_id,
        "session_id": session_id
    }

@app.get("/api/rooms/{room_id}/posts", response_model=List[PostResponse])
async def get_room_posts(
    room_id: str,
    db: Session = Depends(get_db)
):
    """Get all posts in a room organized by threads"""
    room = get_room_with_posts(db, room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found or expired"
        )
    
    # Convert to response format
    posts = []
    for post in getattr(room, 'threaded_posts', []):
        post_response = PostResponse(
            id=post.id,
            content=post.content,
            anonymous_id=post.anonymous_id,
            created_at=post.created_at,
            parent_id=post.parent_id,
            vote_score=post.vote_score,
            replies=[
                PostResponse(
                    id=reply.id,
                    content=reply.content,
                    anonymous_id=reply.anonymous_id,
                    created_at=reply.created_at,
                    parent_id=reply.parent_id,
                    vote_score=reply.vote_score,
                    replies=[]
                )
                for reply in getattr(post, 'replies', [])
            ]
        )
        posts.append(post_response)
    
    return posts

@app.post("/api/rooms/{room_id}/posts", response_model=PostResponse)
async def create_post_endpoint(
    room_id: str,
    post_data: PostCreate,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
):
    
    """Create a new post in a room"""
    # Create and call the auth depednecy manually
    auth_dependency = create_room_auth_dependency(room_id)
    session_data = auth_dependency(request, credentials)
    session_id = session_data["session_id"]

    # Check rate limit
    check_post_rate_limit(session_id)
    
    # Create post

    try:
        post = create_post(db, room_id, session_id, post_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create post"
        )
    
    
    # Prepare response
    post_response = PostResponse(
        id=post.id,
        content=post.content,
        anonymous_id=post.anonymous_id,
        created_at=post.created_at,
        parent_id=post.parent_id,
        vote_score=post.vote_score,
        replies=[]
    )
    
    # Broadcast to room participants
    await broadcast_new_post(room_id, post_response.dict())
    
    return post_response

@app.post("/api/posts/{post_id}/vote", response_model=VoteResponse)
async def vote_on_post_endpoint(
    post_id: str,
    vote_data: VoteCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Vote on a post"""
    session_id = get_session_from_request(request)
    
    # Check rate limit
    check_vote_rate_limit(session_id)
    
    # Cast vote
    vote = vote_on_post(db, post_id, session_id, vote_data)
    
    if not vote:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to vote on post"
        )
    
    # Get updated post
    post = get_post(db, post_id)
    
    response = VoteResponse(
        post_id=post_id,
        vote_type=vote.vote_type,
        new_score=post.vote_score
    )
    
    # Broadcast vote update to room
    await broadcast_new_vote(post.room_id, {
        "post_id": post_id,
        "new_score": post.vote_score
    })
    
    return response

# WebSocket endpoint for real-time communication
@app.websocket("/api/rooms/{room_id}/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    session_id: str = None,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time room communication
    Handles connection lifecycle and message broadcasting
    """
    # Verify room exists
    room = get_room(db, room_id)
    if not room:
        await websocket.close(code=4004, reason="Room not found or expired")
        return
    
    # Get session ID from query parameter or generate new one
    if not session_id:
        session_id = generate_session_id()
    
    # Join room as participant
    participant = join_room(db, room_id, session_id)
    if not participant:
        await websocket.close(code=4003, reason="Cannot join room")
        return
    
    # Handle WebSocket connection
    await handle_websocket_connection(websocket, room_id, session_id)

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)