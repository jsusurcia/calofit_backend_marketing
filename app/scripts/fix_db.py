import sys
import os

# Add the root project directory to the path so we can import 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import SessionLocal
from sqlalchemy import text

def add_column():
    db = SessionLocal()
    try:
        # Check if column exists first to be safe
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='clients' AND column_name='meal_reminder_time';")).fetchone()
        if not result:
            print("Adding meal_reminder_time column to clients table...")
            db.execute(text("ALTER TABLE clients ADD COLUMN meal_reminder_time VARCHAR;"))
            db.commit()
            print("Column added successfully.")
        else:
            print("Column already exists.")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    add_column()
