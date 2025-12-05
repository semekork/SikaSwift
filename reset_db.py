from sqlmodel import SQLModel, create_engine, text
from dotenv import load_dotenv
import os

# 1. Load Environment Variables
load_dotenv()

# 2. Get Database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing from .env file")

# 3. Create Engine
engine = create_engine(DATABASE_URL)

def reset_database():
    print("🔄 Resetting Database...")
    
    with engine.connect() as conn:
        # Step 1: Drop the entire public schema (Nuclear Option)
        # This deletes ALL tables, types, and data immediately.
        conn.execute(text("DROP SCHEMA public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        
        # Step 2: Grant permissions back (Important for Postgres)
        conn.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
        
        conn.commit()
    
    print("✅ Old tables dropped.")

    # Step 3: Create new tables based on your SQLModel classes
    # Import your models here so SQLModel knows about them!
    from models import Transaction, User  # <--- Make sure this import exists!
    
    SQLModel.metadata.create_all(engine)
    print("✅ New tables created successfully.")

if __name__ == "__main__":
    try:
        reset_database()
        print("🚀 Database reset complete!")
    except Exception as e:
        print(f"❌ Error resetting database: {e}")