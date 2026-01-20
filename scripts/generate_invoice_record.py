from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from models.user import Customer
from models.subscription import Payment, Invoice

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def create_missing_invoice():
    print("Finding latest customer...")
    customer = db.query(Customer).order_by(Customer.id.desc()).first()
    if not customer:
        print("No customer found.")
        return

    print(f"Customer: {customer.first_name} {customer.last_name} (ID: {customer.id})")

    # Find the latest payment
    payment = db.query(Payment).filter(Payment.customer_id == customer.id).order_by(Payment.id.desc()).first()
    
    if not payment:
        print("No payments found for this customer.")
        return

    print(f"Latest Payment: ${payment.amount} (Tx ID: {payment.square_transaction_id})")

    # Check if invoice exists for this transaction (using tx id as proxy for invoice id)
    existing_invoice = db.query(Invoice).filter(
        Invoice.square_invoice_id == payment.square_transaction_id
    ).first()

    if existing_invoice:
        print("Invoice already exists for this payment.")
        return

    print("Creating missing Invoice record...")
    
    # We use the transaction ID as the square_invoice_id locally so it's unique
    new_invoice = Invoice(
        customer_id=customer.id,
        square_invoice_id=payment.square_transaction_id, # Using tx ID as placeholder
        subscription_id=customer.square_subscription_id,
        amount=payment.amount,
        status="PAID",
        due_date=payment.created_at,
        public_url=None # No public URL for this backfilled record
    )
    
    db.add(new_invoice)
    db.commit()
    print("Success: Invoice created.")

if __name__ == "__main__":
    create_missing_invoice()
