import os
from dotenv import load_dotenv
load_dotenv()

from db.init import SessionLocal
from models.user import Customer
from models.subscription import SubscriptionLog, SubscriptionPlan

db = SessionLocal()

subs = [
    "ab793446-e780-47f6-af95-ebb7fc5bd3a9",
    "41c0aa4a-ff1e-4808-b053-a6211047b518",
    "59385a8d-ae42-445b-b67c-1fd7877a38f5"
]

customers = db.query(Customer).filter(Customer.square_subscription_id.in_(subs)).all()

with open("db_results.txt", "w") as f:
    f.write(f"Fetching {len(customers)} customers with these subscription IDs...\n")
    for c in customers:
        f.write(f"\n--- Customer: {c.first_name} {c.last_name} (ID: {c.id}) ---\n")
        f.write(f"Plan ID in DB: {c.plan_id}\n")
        f.write(f"Plan Variation ID in DB: {c.plan_variation_id}\n")
        f.write(f"Selected Addons: {c.selected_addons}\n")
        
        logs = db.query(SubscriptionLog).filter(SubscriptionLog.customer_id == c.id).order_by(SubscriptionLog.created_at).all()
        f.write("Logs:\n")
        for l in logs:
            f.write(f"  - {l.action} at {l.created_at} for sub={l.subscription_id}\n")

    f.write("\nFetching testing plan in DB...\n")
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_variation_id == "53ABOOLFZ2RXVLQB4UWNED3Y").first()
    if plan:
        f.write(f"Testing Plan exists in DB! ID: {plan.id}, Name: {plan.plan_name}\n")
    else:
        f.write("Testing plan is not in local DB SubscriptionPlan table.\n")

db.close()
