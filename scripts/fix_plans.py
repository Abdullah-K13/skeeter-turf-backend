from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
import sys

# Add parent directory to path so we can import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from models.subscription import ItemVariation

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL not set in environment")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def fix_db():
    print("Checking for 'Test plan' case mismatch...")
    
    # Check for the lowercase version
    item = db.query(ItemVariation).filter(
        ItemVariation.item_type == "PLAN",
        ItemVariation.name == "Test plan"
    ).first()
    
    if item:
        print(f"Found item with name '{item.name}'. Updating to 'Test Plan'...")
        item.name = "Test Plan"
        db.commit()
        print("Update successful.")
    else:
        # Check if it was already fixed
        item_fixed = db.query(ItemVariation).filter(
            ItemVariation.item_type == "PLAN",
            ItemVariation.name == "Test Plan"
        ).first()
        
        if item_fixed:
            print("Item already correct: 'Test Plan' exists.")
        else:
            print("Error: Could not find 'Test plan' or 'Test Plan' item.")

if __name__ == "__main__":
    fix_db()
