from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def dump_db():
    if not DATABASE_URL:
        print("DATABASE_URL not found.")
        return

    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        print("\n--- SUBSCRIPTION PLANS ---")
        plans = conn.execute(text("SELECT id, plan_name, plan_variation_id FROM subscription_plans;")).fetchall()
        for p in plans:
            print(f"ID: {p[0]} | Name: '{p[1]}' | Variation: {p[2]}")
            
        print("\n--- ITEM VARIATIONS ---")
        items = conn.execute(text("SELECT id, item_type, name, variation_id, price FROM item_variations;")).fetchall()
        for i in items:
            print(f"ID: {i[0]} | Type: {i[1]} | Name: '{i[2]}' | Variation: {i[3]} | Price: ${i[4]:.2f}")

if __name__ == "__main__":
    dump_db()
