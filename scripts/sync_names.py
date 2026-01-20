from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def update_names():
    if not DATABASE_URL:
        print("DATABASE_URL not found.")
        return

    engine = create_engine(DATABASE_URL)
    
    updates = [
        ("Monthly Mosquito Package", "Mosquito Control"),
        ("Monthly Turf Package", "Lawn Care"),
        ("Combo Mosquito / Turf Package", "Complete Bundle")
    ]
    
    with engine.begin() as conn:
        for new_name, old_name in updates:
            result = conn.execute(text("UPDATE item_variations SET name = :new WHERE name = :old AND item_type = 'PLAN';"), 
                         {"new": new_name, "old": old_name})
            print(f"Updated '{old_name}' to '{new_name}' ({result.rowcount} rows affected)")

if __name__ == "__main__":
    update_names()
