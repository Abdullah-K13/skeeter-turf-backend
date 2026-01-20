from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from models.user import Customer
from utils.square_client import search_subscriptions

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def compare_stats():
    print("--- Local Database Stats ---")
    local_active_count = db.query(Customer).filter(Customer.subscription_active == True).count()
    print(f"Local Active Subscribers: {local_active_count}")
    
    local_customers = db.query(Customer).filter(Customer.subscription_active == True).all()
    for c in local_customers:
        print(f"  - Customer ID: {c.id}, Square ID: {c.square_customer_id}, Plan ID: {c.plan_id}")

    print("\n--- Square API Stats ---")
    try:
        res = search_subscriptions(status="ACTIVE")
        if res.get("success"):
            subs = res.get("subscriptions", [])
            print(f"Square Active Subscribers: {len(subs)}")
            for s in subs:
                print(f"  - Sub ID: {s.get('id')}, Cust ID: {s.get('customer_id')}")
        else:
            print(f"Square API Error: {res.get('error')}")
    except Exception as e:
        print(f"Exception calling Square API: {e}")

if __name__ == "__main__":
    compare_stats()
