from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Set
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages WebSocket connections for real-time communication
    Handles room-based broadcasting and connection lifecycle
    """
    
    def __init__(self):
        # Store active connections by room_id
        self.room_connections: Dict[str, Set[WebSocket]] = {}
        # Store session info for each connection
        self.connection_sessions: Dict[WebSocket, dict] = {}
    
    async def connect(self, websocket: WebSocket, room_id: str, session_id: str):
        """Accept new WebSocket connection and add to room"""
        await websocket.accept()
        
        # Add to room connections
        if room_id not in self.room_connections:
            self.room_connections[room_id] = set()
        
        self.room_connections[room_id].add(websocket)
        self.connection_sessions[websocket] = {
            "room_id": room_id,
            "session_id": session_id
        }
        
        logger.info(f"WebSocket connected: session {session_id} joined room {room_id}")
        
        # Notify room about new participant
        await self.broadcast_to_room(room_id, {
            "type": "user_joined",
            "data": {
                "participant_count": len(self.room_connections[room_id])
            }
        }, exclude_websocket=websocket)
    
    async def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection"""
        if websocket in self.connection_sessions:
            session_info = self.connection_sessions[websocket]
            room_id = session_info["room_id"]
            
            # Remove from room connections
            if room_id in self.room_connections:
                self.room_connections[room_id].discard(websocket)
                
                # Clean up empty room
                if not self.room_connections[room_id]:
                    del self.room_connections[room_id]
                else:
                    # Notify remaining participants
                    await self.broadcast_to_room(room_id, {
                        "type": "user_left",
                        "data": {
                            "participant_count": len(self.room_connections[room_id])
                        }
                    })
            
            # Remove session info
            del self.connection_sessions[websocket]
            
            logger.info(f"WebSocket disconnected: session left room {room_id}")
    
    async def broadcast_to_room(self, room_id: str, message: dict, exclude_websocket: WebSocket = None):
        """Send message to all connections in a room"""
        if room_id not in self.room_connections:
            return
        
        # Convert message to JSON
        message_json = json.dumps(message)
        
        # Get all connections for this room
        connections = self.room_connections[room_id].copy()
        
        # Remove the excluded websocket if specified
        if exclude_websocket:
            connections.discard(exclude_websocket)
        
        # Send to all connections
        if connections:
            await asyncio.gather(
                *[self._safe_send(websocket, message_json) for websocket in connections],
                return_exceptions=True
            )
    
    async def _safe_send(self, websocket: WebSocket, message: str):
        """Safely send message to WebSocket with error handling"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
            # Remove the problematic connection
            await self.disconnect(websocket)
    
    async def send_to_session(self, room_id: str, session_id: str, message: dict):
        """Send message to specific session in a room"""
        if room_id not in self.room_connections:
            return
        
        message_json = json.dumps(message)
        
        # Find WebSocket for this session
        for websocket in self.room_connections[room_id]:
            if websocket in self.connection_sessions:
                if self.connection_sessions[websocket]["session_id"] == session_id:
                    await self._safe_send(websocket, message_json)
                    break
    
    def get_room_participant_count(self, room_id: str) -> int:
        """Get count of active WebSocket connections in room"""
        return len(self.room_connections.get(room_id, set()))
    
    def get_active_rooms(self) -> List[str]:
        """Get list of rooms with active connections"""
        return list(self.room_connections.keys())
    
    async def notify_room_expiring(self, room_id: str, minutes_remaining: int):
        """Notify all participants that room is about to expire"""
        await self.broadcast_to_room(room_id, {
            "type": "room_expiring",
            "data": {
                "minutes_remaining": minutes_remaining,
                "message": f"This room will expire in {minutes_remaining} minutes"
            }
        })
    
    async def notify_room_expired(self, room_id: str):
        """Notify all participants that room has expired and close connections"""
        await self.broadcast_to_room(room_id, {
            "type": "room_expired",
            "data": {
                "message": "This room has expired and will be closed"
            }
        })
        
        # Close all connections in this room
        if room_id in self.room_connections:
            connections = self.room_connections[room_id].copy()
            for websocket in connections:
                try:
                    await websocket.close(code=1000, reason="Room expired")
                except:
                    pass
            
            # Clean up
            del self.room_connections[room_id]

# Global connection manager instance
connection_manager = ConnectionManager()

# WebSocket message types for real-time updates
class WebSocketMessageType:
    NEW_POST = "new_post"
    NEW_VOTE = "new_vote"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    ROOM_EXPIRING = "room_expiring"
    ROOM_EXPIRED = "room_expired"
    POST_UPDATED = "post_updated"
    ERROR = "error"

async def handle_websocket_connection(websocket: WebSocket, room_id: str, session_id: str):
    """
    Handle individual WebSocket connection lifecycle
    Manages connection, message handling, and cleanup
    """
    try:
        # Connect to room
        await connection_manager.connect(websocket, room_id, session_id)
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from client
                data = await websocket.receive_text()
                
                # Parse message
                try:
                    message = json.loads(data)
                    await handle_websocket_message(websocket, room_id, session_id, message)
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({
                        "type": WebSocketMessageType.ERROR,
                        "data": {"message": "Invalid JSON format"}
                    }))
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await websocket.send_text(json.dumps({
                    "type": WebSocketMessageType.ERROR,
                    "data": {"message": "Internal server error"}
                }))
    
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    
    finally:
        # Clean up connection
        await connection_manager.disconnect(websocket)

async def handle_websocket_message(websocket: WebSocket, room_id: str, session_id: str, message: dict):
    """
    Handle incoming WebSocket messages from clients
    Currently just handles ping/pong for connection health
    """
    message_type = message.get("type")
    
    if message_type == "ping":
        # Respond to ping with pong
        await websocket.send_text(json.dumps({
            "type": "pong",
            "data": {"timestamp": message.get("data", {}).get("timestamp")}
        }))
    
    elif message_type == "heartbeat":
        # Update last seen timestamp for this session
        # This could be used to track active users
        pass
    
    else:
        # Unknown message type
        await websocket.send_text(json.dumps({
            "type": WebSocketMessageType.ERROR,
            "data": {"message": f"Unknown message type: {message_type}"}
        }))

# Helper functions for broadcasting updates
async def broadcast_new_post(room_id: str, post_data: dict):
    """Broadcast new post to all room participants"""
    await connection_manager.broadcast_to_room(room_id, {
        "type": WebSocketMessageType.NEW_POST,
        "data": post_data
    })

async def broadcast_new_vote(room_id: str, vote_data: dict):
    """Broadcast vote update to all room participants"""
    await connection_manager.broadcast_to_room(room_id, {
        "type": WebSocketMessageType.NEW_VOTE,
        "data": vote_data
    })

async def broadcast_post_updated(room_id: str, post_data: dict):
    """Broadcast post update (like vote score change) to all room participants"""
    await connection_manager.broadcast_to_room(room_id, {
        "type": WebSocketMessageType.POST_UPDATED,
        "data": post_data
    })