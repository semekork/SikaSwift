from sqlmodel import SQLModel, create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS transaction CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS user CASCADE;"))
    conn.commit()
    print("Database Reset Complete. Restart main.py!")