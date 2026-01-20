from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from models.user import Customer
from models.subscription import Payment, SubscriptionLog, Invoice, SubscriptionPlan

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def verify_latest_signup():
    print("--- Latest Customer ---")
    # Get the most recently created customer
    customer = db.query(Customer).order_by(Customer.id.desc()).first()
    
    if not customer:
        print("No customers found.")
        return

    print(f"ID: {customer.id}")
    print(f"Name: {customer.first_name} {customer.last_name}")
    print(f"Email: {customer.email}")
    print(f"Square Customer ID: {customer.square_customer_id}")
    print(f"Square Subscription ID: {customer.square_subscription_id}")
    print(f"Subscription Active: {customer.subscription_active}")
    print(f"Status: {customer.subscription_status}")
    
    print("\n--- Recent Payments (Local DB) ---")
    payments = db.query(Payment).filter(Payment.customer_id == customer.id).all()
    if payments:
        for p in payments:
            print(f"Payment ID: {p.id}, Amount: {p.amount}, Status: {p.status}, Tx ID: {p.square_transaction_id}")
    else:
        print("No local payments found.")

    print("\n--- Subscription Logs (Local DB) ---")
    logs = db.query(SubscriptionLog).filter(SubscriptionLog.customer_id == customer.id).all()
    if logs:
        for l in logs:
            print(f"Action: {l.action}, Date: {l.effective_date}")
    else:
        print("No logs found.")
        
    print("\n--- Invoices (Local DB - Used for Billing History) ---")
    invoices = db.query(Invoice).filter(Invoice.customer_id == customer.id).all()
    if invoices:
        for i in invoices:
            print(f"Inv ID: {i.id}, Square ID: {i.square_invoice_id}, Status: {i.status}")
    else:
        print("No local invoices found. (Billing history may fall back to Square API)")

if __name__ == "__main__":
    verify_latest_signup()
