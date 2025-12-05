from sqlmodel import SQLModel, create_engine, Session
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

engine = create_engine(DATABASE_URL, echo=True)

def init_db():
    """
    Creates the tables defined in models.py.
    """
    try: 
        SQLModel.metadata.create_all(engine)
        print("Database tables created successfully.")
    except Exception as e:
        print(f"Error creating database tables: {e}")

def get_session():
    """
    Dependency to get a DB session per request.
    """
    with Session(engine) as session:
        yield session