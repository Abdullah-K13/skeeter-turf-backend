from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from db.init import get_db
from models.user import Customer, Admin
from models.subscription import SubscriptionPlan
from utils.deps import get_current_user
from pydantic import BaseModel
from datetime import datetime

from datetime import datetime, timedelta

# Simple in-memory cache for stats
_stats_cache = {"count": 0, "expires": datetime.min}

router = APIRouter(prefix="", tags=["admin"])

class CustomerListItem(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    plan: str
    status: str
    amount: float
    lastPayment: str
    address: str
    city: str
    zip: str

class StatsResponse(BaseModel):
    active_subscribers: int

@router.get("/stats", response_model=StatsResponse)
def get_admin_stats(
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can access this resource"
        )
    
    global _stats_cache
    if datetime.now() < _stats_cache["expires"]:
        return StatsResponse(active_subscribers=_stats_cache["count"])

    from utils.square_client import search_subscriptions
    res = search_subscriptions(status="ACTIVE")
    
    count = 0
    if res.get("success"):
        count = res.get("count", 0)
        # Cache for 5 minutes
        _stats_cache = {
            "count": count,
            "expires": datetime.now() + timedelta(minutes=5)
        }
    else:
        # Fallback to last known cache if Square fails
        return StatsResponse(active_subscribers=_stats_cache["count"])
        
    return StatsResponse(active_subscribers=count)

@router.get("/customers", response_model=List[CustomerListItem])
def list_customers(
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    # Check if current_user role is indeed set to "admin" in JWT payload
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can access this resource"
        )
    
    from sqlalchemy import func
    from models.subscription import Payment
    
    # Optimized fetch: get all customers, plans, and last payments in bulk
    customers = db.query(Customer).all()
    all_plans = {p.id: p for p in db.query(SubscriptionPlan).all()}
    
    # Get all last payments in one query
    last_payments = db.query(
        Payment.customer_id,
        func.max(Payment.created_at)
    ).group_by(Payment.customer_id).all()
    last_payment_map = {cid: dt for cid, dt in last_payments}

    result = []
    for c in customers:
        plan_name = "No Plan"
        plan_cost = 0.0
        
        try:
            pid = int(c.plan_id) if c.plan_id else None
            if pid and pid in all_plans:
                plan_name = all_plans[pid].plan_name
                plan_cost = all_plans[pid].plan_cost
        except (ValueError, TypeError):
            pass

        last_payment_date = last_payment_map.get(c.id)
        last_payment_str = last_payment_date.strftime("%Y-%m-%d") if last_payment_date else "N/A"

        result.append(CustomerListItem(
            id=c.id,
            name=f"{c.first_name} {c.last_name}",
            email=c.email,
            phone=c.phone_number or "",
            plan=plan_name,
            status="Active" if c.subscription_active else "Inactive",
            amount=plan_cost,
            lastPayment=last_payment_str,
            address=c.address or "",
            city=c.city or "",
            zip=c.zip_code or ""
        ))
    
    return result

@router.post("/cancel-subscription/{customer_id}")
def cancel_customer_subscription(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    customer = db.query(Customer).get(customer_id)
    if not customer or not customer.square_subscription_id:
        raise HTTPException(status_code=404, detail="Active subscription not found")
    
    from utils.square_client import cancel_subscription
    res = cancel_subscription(customer.square_subscription_id)
    
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=f"Square error: {res.get('error')}")
    
    # Update local state
    customer.subscription_active = False
    customer.subscription_status = "CANCELED"
    db.commit()
    
    return {"success": True, "message": "Subscription canceled"}

@router.get("/customer-cards/{customer_id}")
def get_customer_cards(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    customer = db.query(Customer).get(customer_id)
    if not customer or not customer.square_customer_id:
        raise HTTPException(status_code=404, detail="Square customer not found")
    
    from utils.square_client import get_customer_cards
    res = get_customer_cards(customer.square_customer_id)
    
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=f"Square error: {res.get('error')}")
    
    return res

@router.post("/remove-card/{customer_id}/{card_id}")
def remove_customer_card(
    customer_id: int,
    card_id: str,
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    from utils.square_client import disable_card
    res = disable_card(card_id)
    
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=f"Square error: {res.get('error')}")
    
    return {"success": True, "message": "Card removed"}

class UpdateCustomerRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone_number: str
    address: str
    city: str
    zip_code: str

@router.put("/customer-details/{customer_id}")
def update_customer_details(
    customer_id: int,
    request: UpdateCustomerRequest,
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    customer = db.query(Customer).get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Update Square if ID exists
    if customer.square_customer_id:
        from utils.square_client import update_square_customer
        sq_res = update_square_customer(
            customer.square_customer_id,
            given_name=request.first_name,
            family_name=request.last_name,
            email_address=request.email,
            phone_number=request.phone_number,
            address={
                "address_line_1": request.address,
                "locality": request.city,
                "postal_code": request.zip_code
            }
        )
        if not sq_res.get("success"):
            # We skip erroring here if it's just a sync issue, or we can enforce it.
            # Let's enforce for now.
            raise HTTPException(status_code=400, detail=f"Square sync error: {sq_res.get('error')}")

    # Update local DB
    customer.first_name = request.first_name
    customer.last_name = request.last_name
    customer.email = request.email
    customer.phone_number = request.phone_number
    customer.address = request.address
    customer.city = request.city
    customer.zip_code = request.zip_code
    
    db.commit()
    return {"success": True, "message": "Customer details updated"}

@router.get("/customer-payments/{customer_id}")
def get_customer_payments(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    customer = db.query(Customer).get(customer_id)
    if not customer or not customer.square_customer_id:
        raise HTTPException(status_code=404, detail="Square customer not found")
    
    from utils.square_client import get_customer_invoices
    res = get_customer_invoices(customer.square_customer_id)
    
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=f"Square error: {res.get('error')}")
    
    return res
