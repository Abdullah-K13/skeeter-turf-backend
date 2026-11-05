from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from db.init import get_db
from models.user import Customer
from models.subscription import SubscriptionLog
from datetime import date
import base64
import hashlib
import hmac
import json
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_square_signature(signature: str, body: bytes) -> bool:
    """Square signs HMAC-SHA256 over (notification_url + raw body), base64 encoded.

    Fails closed: without both env vars configured, no webhook is accepted. Nothing
    breaks by doing this today because Square currently has zero webhook subscriptions
    pointed at this backend - set both when you create one.
    """
    key = os.getenv("SQUARE_WEBHOOK_SIGNATURE_KEY")
    url = os.getenv("SQUARE_WEBHOOK_URL")
    if not key or not url:
        logger.error("SQUARE_WEBHOOK_SIGNATURE_KEY / SQUARE_WEBHOOK_URL not set - rejecting webhook")
        return False
    expected = base64.b64encode(
        hmac.new(key.encode(), url.encode() + body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, signature or "")

@router.post("/square")
async def square_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle webhooks from Square.
    Events: invoice.scheduled_charge_failed, invoice.payment_made, subscription.updated
    (names taken from GET /v2/webhooks/event-types - "invoice.payment_failed" and
    "invoice.payment_succeeded" are not events Square emits and never fired.)
    """
    body = await request.body()
    if not verify_square_signature(request.headers.get("x-square-hmacsha256-signature"), body):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    payload = json.loads(body)
    event_type = payload.get("type")
    data = payload.get("data", {}).get("object", {})
    
    logger.info(f"Received Square webhook: {event_type}")

    if event_type == "invoice.scheduled_charge_failed":
        invoice = data.get("invoice", {})
        # Square invoices carry no top-level customer_id - it lives on primary_recipient.
        customer_id = (invoice.get("primary_recipient") or {}).get("customer_id")
        
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
                        action="SUSPEND_3_FAILED_PAYMENTS",
                        effective_date=date.today(),
                    )
                    db.add(log)
                    logger.error(f"Customer {customer.id} has been SUSPENDED due to 3 failed payments.")
                
                db.commit()

    elif event_type == "subscription.updated":
        # Keeps the local status honest when a subscription is canceled/paused/resumed
        # anywhere other than this backend (e.g. the Square dashboard).
        sub = data.get("subscription", {})
        status = sub.get("status")
        if sub.get("id") and status:
            customer = db.query(Customer).filter(Customer.square_subscription_id == sub["id"]).first()
            if customer and customer.subscription_status != status:
                logger.info(f"Customer {customer.id}: subscription {sub['id']} is {status} in Square, was {customer.subscription_status}")
                customer.subscription_status = status
                customer.subscription_active = status == "ACTIVE"
                log = SubscriptionLog(
                    customer_id=customer.id,
                    subscription_id=sub["id"],
                    action=f"SQUARE_{status}",
                    effective_date=date.today(),
                )
                db.add(log)
                db.commit()

    elif event_type == "invoice.payment_made":
        invoice = data.get("invoice", {})
        # Square invoices carry no top-level customer_id - it lives on primary_recipient.
        customer_id = (invoice.get("primary_recipient") or {}).get("customer_id")
        
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

                # Record the invoice itself. Nothing else does this automatically:
                # the invoices table used to be filled only when an admin opened the
                # View Invoices dialog for one customer at a time, so customers nobody
                # clicked on had no local billing history at all.
                from utils.invoice_sync import sync_invoices_for_customer
                sync_res = sync_invoices_for_customer(db, customer)
                if not sync_res.get("success"):
                    logger.error(f"Invoice sync failed for customer {customer.id}: {sync_res.get('error')}")

    return {"status": "ok"}
