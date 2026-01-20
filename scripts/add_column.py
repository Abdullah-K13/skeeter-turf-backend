from sqlalchemy import text
import sys
import os

# Add parent directory to path to import db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.init import engine

def add_column():
    print("Attempting to add 'failed_payment_attempts' column to 'customers' table...")
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE customers ADD COLUMN failed_payment_attempts INTEGER DEFAULT 0"))
            conn.commit()
            print("Successfully added 'failed_payment_attempts' column.")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("Column 'failed_payment_attempts' already exists.")
            else:
                print(f"Error adding column: {e}")

if __name__ == "__main__":
    add_column()
