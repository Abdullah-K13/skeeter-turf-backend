from sqlalchemy import create_engine, text
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def add_billing_type_column():
    if not DATABASE_URL:
        print("DATABASE_URL not found.")
        return

    engine = create_engine(DATABASE_URL)
    
    print("Adding billing_type column to item_variations...")
    
    with engine.begin() as conn: 
        try:
            # Add the column with a default value of 'RECURRING'
            conn.execute(text("ALTER TABLE item_variations ADD COLUMN billing_type VARCHAR(50) DEFAULT 'RECURRING';"))
            print("Successfully added 'billing_type' column.")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("Column 'billing_type' already exists.")
            else:
                print(f"Error adding column: {e}")

if __name__ == "__main__":
    add_billing_type_column()
