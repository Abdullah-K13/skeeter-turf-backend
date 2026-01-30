import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

# Add current directory to path
sys.path.append(os.getcwd())

from db.init import Base
from models.user import Customer
from models.subscription import SubscriptionPlan, ItemVariation

# Setup DB Connection (Assuming local sqlite or env vars are set, but usually main.py has logic)
# We need to see how db.init gets the URL.
# Let's peek at db/init.py first or just try to import SessionLocal
try:
    from db.init import SessionLocal
except ImportError:
    print("Could not import SessionLocal. Please run from project root.")
    sys.exit(1)

def verify_analytics():
    db = SessionLocal()
    try:
        print("--- Verifying Analytics Logic ---")
        
        # 1. Fetch Necessary Data
        all_plans = db.query(SubscriptionPlan).all()
        plan_map = {p.plan_variation_id: p for p in all_plans if p.plan_variation_id}
        plan_id_map = {str(p.id): p for p in all_plans}
        
        print(f"Found {len(all_plans)} subscription plans.")

        all_addons = db.query(ItemVariation).filter(ItemVariation.item_type == "ADDON").all()
        addon_map = {a.variation_id: a for a in all_addons}
        print(f"Found {len(all_addons)} addons.")

        active_customers = db.query(Customer).filter(
            Customer.subscription_active == True,
            Customer.subscription_status == "ACTIVE" 
        ).all()
        
        active_sub_count = len(active_customers)
        print(f"Active Subscribers: {active_sub_count}")

        mrr = 0.0
        plan_counts = {}
        
        for customer in active_customers:
            cust_revenue = 0.0
            p_name = "Unknown"
            
            # Plan Cost
            if customer.plan_variation_id and customer.plan_variation_id in plan_map:
                plan = plan_map[customer.plan_variation_id]
                cust_revenue += plan.plan_cost
                p_name = plan.plan_name
            elif customer.plan_id and customer.plan_id in plan_id_map:
                plan = plan_id_map[customer.plan_id]
                cust_revenue += plan.plan_cost
                p_name = plan.plan_name
            
            # Addon Cost
            if customer.selected_addons:
                for addon_id in customer.selected_addons:
                    if addon_id in addon_map:
                        cust_revenue += addon_map[addon_id].price
            
            mrr += cust_revenue
            plan_counts[p_name] = plan_counts.get(p_name, 0) + 1

        print(f"Calculated MRR: ${mrr:.2f}")
        print("Plan Distribution:")
        for name, count in plan_counts.items():
            print(f"  - {name}: {count}")

        # Total Customers
        total = db.query(Customer).count()
        print(f"Total Customers: {total}")

    except Exception as e:
        print(f"Error during verification: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    verify_analytics()
