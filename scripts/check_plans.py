from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
import sys

# Add parent directory to path so we can import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from models.subscription import SubscriptionPlan, ItemVariation

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL not set in environment")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def check_db():
    print("--- Subscription Plans ---")
    plans = db.query(SubscriptionPlan).all()
    for p in plans:
        print(f"Plan: {p.plan_name} (ID: {p.id}, Variation ID: {p.plan_variation_id})")

    print("\n--- Item Variations (PLAN Type) ---")
    items = db.query(ItemVariation).filter(ItemVariation.item_type == "PLAN").all()
    for i in items:
        print(f"Item: {i.name} (Variation ID: {i.variation_id})")

    print("\n--- Items Missing for Plans ---")
    
    plan_names = {p.plan_name for p in plans}
    item_names = {i.name for i in items}
    
    missing = plan_names - item_names
    if missing:
        print(f"FAIL: The following plans are missing a corresponding ItemVariation: {missing}")
    else:
        print("OK: All plans have a corresponding ItemVariation.")

if __name__ == "__main__":
    check_db()
