from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from db.init import Base
from models.subscription import OneTimePlan

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_one_time():
    print("Creating tables for One-Time Payments...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        print("Seeding One-Time Plans...")
        plans_data = [
            {
                "name": "Mosquito Package",
                "price": 80.00,
                "turf_size_label": "1 Acre and under",
                "description": "Professional mosquito treatment for properties 1 acre and under. One-time service."
            },
            {
                "name": "Turf Package",
                "price": 100.00,
                "turf_size_label": "5,000 Sq ft & Under",
                "description": "Professional turf care treatment for properties 5,000 sq ft and under. One-time service."
            },
            {
                "name": "Combo Deal",
                "price": 150.00,
                "turf_size_label": "Best Value",
                "description": "Mosquito + Turf Package. Includes Free Insect & Perimeter Treatment. One-time service."
            }
        ]
        
        for data in plans_data:
            existing = db.query(OneTimePlan).filter(OneTimePlan.name == data["name"]).first()
            if not existing:
                plan = OneTimePlan(**data)
                db.add(plan)
                print(f"Added plan: {data['name']}")
            else:
                print(f"Plan already exists: {data['name']}")
        
        db.commit()
        print("Done!")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_one_time()
