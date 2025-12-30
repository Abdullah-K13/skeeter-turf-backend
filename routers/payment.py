from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from db.init import get_db
from models.user import Customer
from models.subscription import SubscriptionPlan, Payment, PaymentMethod, SubscriptionLog
from utils.deps import get_current_user, get_db_user
from utils.square_client import (
    get_subscription_plans,
    create_square_customer,
    create_card_on_file,
    create_subscription,
    get_subscriptions,
    cancel_subscription,
    update_subscription,
    pause_subscription,
    resume_subscription,
    get_customer_invoices
)
from pydantic import BaseModel
import os
import uuid
from datetime import date
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Pydantic Models ---

class ValidateCardRequest(BaseModel):
    source_id: str
    customer_id: Optional[int] = None # Local DB ID
    # If customer_id is not provided, we might need these to create one
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None

class ActivateSubscriptionRequest(BaseModel):
    plan_variation_id: str
    customer_id: Optional[int] = None # Local DB ID
    card_id: str
    location_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    start_date: Optional[str] = None

class ChangePlanRequest(BaseModel):
    new_plan_variation_id: str

# --- Endpoints ---

@router.get("/square-config")
def get_square_config():
    return {
        "application_id": os.getenv("SQUARE_APPLICATION_ID", ""),
        "location_id": os.getenv("SQUARE_LOCATION_ID", "")
    }

@router.get("/subscription-plans")
def get_square_plans():
    """Fetch all subscription plans directly from Square Catalog."""
    result = get_subscription_plans()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result

@router.get("/subscription-plans/db")
def get_db_plans(db: Session = Depends(get_db)):
    """Fetch all subscription plans from local database."""
    plans = db.query(SubscriptionPlan).all()
    return {"success": True, "plans": plans}

@router.post("/validate-card")
def validate_card(request: ValidateCardRequest, db: Session = Depends(get_db)):
    """
    1. Create/Get Square Customer.
    2. Attach Card to Square Customer.
    3. Return card_id and customer info.
    """
    customer = None
    if request.customer_id:
        customer = db.query(Customer).get(request.customer_id)
    
    # If no local customer found, we might be in a guest checkout or first step
    # But usually, we want to link it to a local user.
    
    sq_customer_id = customer.square_customer_id if customer else None
    
    if not sq_customer_id:
        # Create Square Customer
        given_name = request.given_name or (customer.first_name if customer else "Guest")
        family_name = request.family_name or (customer.last_name if customer else "User")
        email = request.email or (customer.email if customer else f"guest_{uuid.uuid4().hex[:8]}@example.com")
        
        res = create_square_customer(
            given_name=given_name,
            family_name=family_name,
            email=email,
            phone_number=request.phone_number or (customer.phone_number if customer else None)
        )
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=f"Square customer creation failed: {res.get('error')}")
        sq_customer_id = res.get("customer_id")
        
        if customer:
            customer.square_customer_id = sq_customer_id
            db.commit()

    # Attach Card
    card_res = create_card_on_file(
        source_id=request.source_id,
        customer_id=sq_customer_id
    )
    
    if not card_res.get("success"):
        raise HTTPException(status_code=400, detail=f"Card validation failed: {card_res.get('error')}")

    # Save Payment Method to DB if customer exists
    if customer:
        new_method = PaymentMethod(
            customer_id=customer.id,
            square_card_id=card_res.get("card_id"),
            last_4_digits=card_res.get("last_4"),
            card_brand=card_res.get("brand"),
            exp_month=card_res.get("exp_month"),
            exp_year=card_res.get("exp_year"),
            is_default=True
        )
        # Set others to not default
        db.query(PaymentMethod).filter(PaymentMethod.customer_id == customer.id).update({"is_default": False})
        db.add(new_method)
        db.commit()

    return {
        "success": True,
        "card_id": card_res.get("card_id"),
        "customer_id": sq_customer_id,
        "card_details": card_res
    }

def dummy_create_subscription(customer_id: str, location_id: str, plan_variation_id: str, card_id: str, **kwargs) -> Dict[str, Any]:
    """Helper for testing to skip real Square call"""
    return {
        "success": True,
        "subscription_id": f"dummy_sub_{uuid.uuid4().hex[:12]}",
        "subscription": {"status": "ACTIVE"}
    }

@router.post("/activate-subscription")
def activate_sub(request: ActivateSubscriptionRequest, db: Session = Depends(get_db)):
    customer = None
    if request.customer_id:
        customer = db.query(Customer).get(request.customer_id)
    
    sq_customer_id = customer.square_customer_id if customer else None
    if not sq_customer_id:
        raise HTTPException(status_code=400, detail="Square customer ID missing")

    location_id = request.location_id or os.getenv("SQUARE_LOCATION_ID")
    
    # Create subscription using dummy function
    res = dummy_create_subscription(
        customer_id=sq_customer_id,
        location_id=location_id,
        plan_variation_id=request.plan_variation_id,
        card_id=request.card_id,
        idempotency_key=request.idempotency_key,
        start_date=request.start_date
    )
    
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=f"Subscription failed: {res.get('error')}")

    if customer:
        customer.square_subscription_id = res.get("subscription_id")
        customer.subscription_active = True
        customer.subscription_status = "ACTIVE"
        db.commit()
        
        # Log payment locally
        # We assume the first payment is taken immediately by Square
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_variation_id == request.plan_variation_id).first()
        if plan:
            new_payment = Payment(
                customer_id=customer.id,
                amount=plan.plan_cost,
                status="PAID",
                square_transaction_id=res.get("subscription_id") # Square uses subscription ID as ref often
            )
            db.add(new_payment)

        # Log action
        log = SubscriptionLog(
            customer_id=customer.id,
            subscription_id=res.get("subscription_id"),
            action="ACTIVATE",
            effective_date=date.today()
        )
        db.add(log)
        db.commit()

    return res

@router.get("/my-subscriptions")
def get_my_subs(user: Customer = Depends(get_db_user)):
    if not user.square_customer_id:
        return {"success": True, "subscriptions": []}
    return get_subscriptions(customer_id=user.square_customer_id)

@router.post("/pause-subscription")
def pause_sub(user: Customer = Depends(get_db_user), db: Session = Depends(get_db)):
    if not user.square_subscription_id:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    res = pause_subscription(user.square_subscription_id)
    if "errors" in res:
        raise HTTPException(status_code=400, detail=str(res["errors"]))
    
    user.subscription_status = "PAUSED"
    log = SubscriptionLog(
        customer_id=user.id,
        subscription_id=user.square_subscription_id,
        action="PAUSE",
        effective_date=date.today()
    )
    db.add(log)
    db.commit()
    return res

@router.post("/resume-subscription")
def resume_sub(user: Customer = Depends(get_db_user), db: Session = Depends(get_db)):
    if not user.square_subscription_id:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    res = resume_subscription(user.square_subscription_id)
    if "errors" in res:
        raise HTTPException(status_code=400, detail=str(res["errors"]))
    
    user.subscription_status = "ACTIVE"
    log = SubscriptionLog(
        customer_id=user.id,
        subscription_id=user.square_subscription_id,
        action="RESUME",
        effective_date=date.today()
    )
    db.add(log)
    db.commit()
    return res

@router.post("/cancel-subscription")
def cancel_sub(user: Customer = Depends(get_db_user), db: Session = Depends(get_db)):
    if not user.square_subscription_id:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    res = cancel_subscription(user.square_subscription_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    
    user.subscription_active = False
    user.subscription_status = "CANCELED"
    log = SubscriptionLog(
        customer_id=user.id,
        subscription_id=user.square_subscription_id,
        action="CANCEL",
        effective_date=date.today()
    )
    db.add(log)
    db.commit()
    return res

@router.post("/change-plan")
def change_plan(request: ChangePlanRequest, user: Customer = Depends(get_db_user), db: Session = Depends(get_db)):
    if not user.square_subscription_id:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    res = update_subscription(user.square_subscription_id, request.new_plan_variation_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    
    return res

@router.get("/billing-history")
def billing_history(user: Customer = Depends(get_db_user)):
    if not user.square_customer_id:
        return {"success": True, "invoices": []}
    return get_customer_invoices(user.square_customer_id)
