from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from db.init import get_db
from models.user import Customer
from models.subscription import SubscriptionLog
from datetime import date
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/square")
async def square_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle webhooks from Square.
    Events: invoice.payment_failed, invoice.payment_succeeded
    """
    payload = await request.json()
    event_type = payload.get("type")
    data = payload.get("data", {}).get("object", {})
    
    logger.info(f"Received Square webhook: {event_type}")

    if event_type == "invoice.payment_failed":
        invoice = data.get("invoice", {})
        customer_id = invoice.get("customer_id")
        
        if customer_id:
            customer = db.query(Customer).filter(Customer.square_customer_id == customer_id).first()
            if customer:
                customer.failed_payment_attempts = (customer.failed_payment_attempts or 0) + 1
                logger.warning(f"Payment failed for customer {customer.id}. Total failures: {customer.failed_payment_attempts}")
                
                if customer.failed_payment_attempts >= 3:
                    customer.subscription_status = "SUSPENDED"
                    customer.subscription_active = False # Mark as inactive if suspended? Or keep active but status suspended.
                    # Usually suspended means "Service stopped until paid"
                    
                    # Log the suspension
                    log = SubscriptionLog(
                        customer_id=customer.id,
                        subscription_id=customer.square_subscription_id,
                        action="SUSPEND",
                        effective_date=date.today(),
                        details="Suspended after 3 failed payment attempts"
                    )
                    db.add(log)
                    logger.error(f"Customer {customer.id} has been SUSPENDED due to 3 failed payments.")
                
                db.commit()

    elif event_type == "invoice.payment_succeeded":
        invoice = data.get("invoice", {})
        customer_id = invoice.get("customer_id")
        
        if customer_id:
            customer = db.query(Customer).filter(Customer.square_customer_id == customer_id).first()
            if customer:
                # Reset failure count on success
                if customer.failed_payment_attempts > 0:
                    logger.info(f"Payment succeeded for customer {customer.id}. Resetting failure count.")
                    customer.failed_payment_attempts = 0
                    
                    # If they were suspended, maybe auto-reactivate? 
                    # For now, just reset the count. Admin might need to manual resume or it might be automatic.
                    if customer.subscription_status == "SUSPENDED":
                         customer.subscription_status = "ACTIVE"
                         customer.subscription_active = True
                
                db.commit()

    return {"status": "ok"}
