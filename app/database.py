from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Datbase Configuration of Postgresql in the app
DATABASE_URL = os.getenv("DATABASE_URL")

# Create database engine
engine = create_engine(DATABASE_URL)

# Sessionmaker for database operations
SessionLocal = sessionmaker(autocommit=False, bind=engine)

# Bse class for models
Base = declarative_base()

def get_db():
    """Databse dependency for FastAPI.
    Creates and manages a database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    # Create all database tables when the app starts up
    from app.models import Base
    Base.metadata.create_all(bind=engine)