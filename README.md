# Ripple Backend

Ripple is a backend API for creating anonymous, temporary chat rooms where users can share thoughts freely and connect authentically. This service powers the Ripple frontend, enabling features like anonymous identities, mood detection, voting, and real-time messaging.

## Features

- **Anonymous Identity:** Users are assigned random identities per room.
- **Temporary Rooms:** Rooms expire after a set duration.
- **Real-Time Messaging:** WebSocket support for live updates.
- **Voting System:** Upvote or downvote posts.
- **Mood Detection:** AI-powered mood analysis for posts.
- **Secure Authentication:** JWT-based authentication for API endpoints.

## Project Structure

```
backend/
    app/
        auth.py
        crud.py
        database.py
        main.py
        models.py
        schemas.py
        websocket.py
    .env
    requirements.txt
    runtime.txt
    README.md
```

## Getting Started

### Prerequisites

- Python 3.12.7 (see [`runtime.txt`](runtime.txt))
- PostgreSQL database
- Redis server (optional, for WebSocket scaling)
- [Poetry](https://python-poetry.org/) or `pip` for dependency management

### Installation

1. **Clone the repository:**

   ```sh
   git clone https://github.com/WisdomEhirim06/Ripple-Backend.git
   cd Ripple-Backend/backend
   ```

2. **Set up environment variables:**

   Copy `.env.example` to `.env` and update values as needed:

   ```
   DATABASE_URL=postgresql://<user>:<password>@<host>/<dbname>
   SECRET_KEY=your-super-secret-key
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_HOURS=24
   ```

3. **Install dependencies:**

   ```sh
   pip install -r requirements.txt
   ```

4. **Run database migrations:**

   ```sh
   alembic upgrade head
   ```

5. **Start the server:**

   ```sh
   uvicorn app.main:app --reload
   ```

   The API will be available at `http://localhost:8000`.

## API Endpoints

- `POST /api/rooms` — Create a new room
- `GET /api/rooms/{room_id}` — Get room details
- `POST /api/rooms/{room_id}/join` — Join a room (assigns anonymous identity)
- `GET /api/rooms/{room_id}/posts` — List posts in a room
- `POST /api/rooms/{room_id}/posts` — Create a new post
- `POST /api/posts/{post_id}/vote` — Vote on a post
- `GET /api/rooms/{room_id}/ws` — WebSocket endpoint for real-time updates

See [`app/schemas.py`](app/schemas.py) for request/response models.

## Development

- Code is organized by feature in the [`app`](app) directory.
- Environment variables are loaded from [`.env`](.env).
- Database models are defined in [`app/models.py`](app/models.py).
- Business logic is in [`app/crud.py`](app/crud.py).
- Authentication is handled in [`app/auth.py`](app/auth.py).
- WebSocket logic is in [`app/websocket.py`](app/websocket.py).

## Deployment

- Ensure your deployment environment uses Python 3.12.x as specified in [`runtime.txt`](runtime.txt).
- Set environment variables securely.
- Use a production-ready ASGI server (e.g., Uvicorn with Gunicorn).
- Configure PostgreSQL and Redis connections as needed.

## License

This project is for educational and demonstration purposes. Please update secrets and configurations before deploying to production.

---

**Enjoy Ripple! Let your voice ripple through the community.**