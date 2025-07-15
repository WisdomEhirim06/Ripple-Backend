from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
import uuid
from typing import Optional

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", "24"))

security = HTTPBearer(auto_error=False)

def create_session_token(session_id: str, room_id: str) -> str:
    """
    Create JWT token for room session
    Contains session_id and room_id for anonymous authentication
    """
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    
    payload = {
        "session_id": session_id,
        "room_id": room_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "room_session"
    }
    
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_session_token(token: str) -> dict:
    """
    Verify and decode JWT session token
    Returns session data if valid, raises exception if invalid
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Check token type
        if payload.get("type") != "room_session":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        return payload
    
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

def generate_session_id() -> str:
    """Generate unique session ID for anonymous users"""
    return str(uuid.uuid4())

def get_session_from_request(request: Request) -> str:
    """
    Extract session ID from request
    First check Authorization header, then cookies, finally generate new
    """
    # Try to get from Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = verify_session_token(token)
            return payload["session_id"]
        except HTTPException:
            pass
    
    # Try to get from cookie
    session_id = request.cookies.get("session_id")
    if session_id:
        return session_id
    
    # Generate new session ID
    return generate_session_id()

class SessionAuth:
    """
    Authentication dependency for room sessions
    Extracts and validates session information
    """
    
    def __init__(self, room_id: str):
        self.room_id = room_id
    
    def __call__(self, 
                 request: Request,
                 credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
        
        session_id = None
        
        # Try to get session from token
        if credentials:
            try:
                payload = verify_session_token(credentials.credentials)
                
                # Verify token is for the correct room
                if payload.get("room_id") != self.room_id:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token not valid for this room"
                    )
                
                session_id = payload["session_id"]
                
            except HTTPException:
                pass
        
        # If no valid token, get/generate session ID
        if not session_id:
            session_id = get_session_from_request(request)
        
        return {
            "session_id": session_id,
            "room_id": self.room_id
        }

def create_room_auth_dependency(room_id: str):
    """Factory function to create room-specific auth dependency"""
    return SessionAuth(room_id)

# Rate limiting helpers
class RateLimiter:
    """Simple in-memory rate limiter for preventing spam"""
    
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}  # {session_id: [(timestamp, count), ...]}
    
    def is_allowed(self, session_id: str) -> bool:
        """Check if request is allowed based on rate limits"""
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.window_seconds)
        
        # Clean old requests
        if session_id in self.requests:
            self.requests[session_id] = [
                (timestamp, count) for timestamp, count in self.requests[session_id]
                if timestamp > window_start
            ]
        else:
            self.requests[session_id] = []
        
        # Count requests in current window
        current_count = sum(count for _, count in self.requests[session_id])
        
        if current_count >= self.max_requests:
            return False
        
        # Add current request
        self.requests[session_id].append((now, 1))
        return True

# Global rate limiters
post_rate_limiter = RateLimiter(max_requests=30, window_seconds=60)  # 30 posts per minute
vote_rate_limiter = RateLimiter(max_requests=100, window_seconds=60)  # 100 votes per minute

def check_post_rate_limit(session_id: str):
    """Check if posting is allowed for this session"""
    if not post_rate_limiter.is_allowed(session_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many posts. Please wait before posting again."
        )

def check_vote_rate_limit(session_id: str):
    """Check if voting is allowed for this session"""
    if not vote_rate_limiter.is_allowed(session_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many votes. Please wait before voting again."
        )