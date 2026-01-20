from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from models.user import Customer
from models.subscription import SubscriptionPlan

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def verify_fix():
    print("--- Verifying Admin Analytics Logic ---")
    
    # 1. Active Customers
    active_customers = db.query(Customer).filter(Customer.subscription_active == True).all()
    active_count = len(active_customers)
    print(f"Active Subscribers: {active_count}")
    
    # 2. Plans
    db_plans = db.query(SubscriptionPlan).all()
    plan_map = {}
    for p in db_plans:
        info = {"name": p.plan_name, "price": p.plan_cost}
        if p.plan_variation_id:
            plan_map[p.plan_variation_id] = info
        plan_map[str(p.id)] = info
        
    print(f"Loaded {len(db_plans)} plans.")
    
    # 3. Calculate MRR
    mrr = 0.0
    plan_counts = {}
    
    for c in active_customers:
        p_name = "Unknown Plan"
        price = 0.0
        
        if c.plan_variation_id and c.plan_variation_id in plan_map:
            p_name = plan_map[c.plan_variation_id]["name"]
            price = plan_map[c.plan_variation_id]["price"]
        elif c.plan_id and str(c.plan_id) in plan_map:
            p_name = plan_map[str(c.plan_id)]["name"]
            price = plan_map[str(c.plan_id)]["price"]
            
        mrr += price
        plan_counts[p_name] = plan_counts.get(p_name, 0) + 1
        
    print(f"MRR: ${mrr:.2f}")
    print(f"Plan Distribution: {plan_counts}")
    
    if active_count > 0:
        print("SUCCESS: Logic produced results.")
    else:
        print("WARNING: Active count is 0 (might be correct if no subs, but expected >0 here)")

if __name__ == "__main__":
    verify_fix()
