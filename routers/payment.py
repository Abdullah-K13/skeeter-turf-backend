from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from db.init import get_db
from models.user import Customer
from models.subscription import SubscriptionPlan, Payment, PaymentMethod, SubscriptionLog, ItemVariation
from utils.deps import get_current_user, get_db_user
from utils.square_client import (
    get_subscription_plans,
    create_square_customer,
    create_card_on_file,
    get_customer_cards,
    disable_card,
    create_subscription,
    get_subscriptions,
    cancel_subscription,
    update_subscription,
    update_subscription_card,
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
    addons: Optional[List[str]] = None

class ChangePlanRequest(BaseModel):
    new_plan_variation_id: str

class SaveCardRequest(BaseModel):
    source_id: str

class OneTimePaymentRequest(BaseModel):
    source_id: str
    customer_info: Dict[str, Any]
    plan_details: Dict[str, Any]
    addons: List[Dict[str, Any]]
    total_amount: float # Total in dollars
    customer_id: Optional[int] = None
    location_id: Optional[str] = None
    idempotency_key: Optional[str] = None

# --- Endpoints ---

@router.get("/one-time-plans")
def get_one_time_plans(db: Session = Depends(get_db)):
    """Fetch all one-time service plans from local database."""
    from models.subscription import OneTimePlan
    plans = db.query(OneTimePlan).all()
    return {"success": True, "plans": plans}

@router.post("/one-time-payment")
def one_time_payment(request: OneTimePaymentRequest, db: Session = Depends(get_db)):
    """Process a one-time payment and record the order."""
    from utils.square_client import process_payment, create_square_customer
    from models.subscription import OneTimeOrder, Payment
    
    # 1. Create/Get Square Customer
    sq_customer_id = None
    customer_info = request.customer_info
    customer_id = request.customer_id
    
    # Check if a customer with this email already exists OR use request.customer_id
    from models.user import Customer
    existing_user = None
    if customer_id:
        existing_user = db.query(Customer).get(customer_id)
    
    if not existing_user:
        existing_user = db.query(Customer).filter(Customer.email == customer_info.get("email")).first()
    
    if existing_user:
        sq_customer_id = existing_user.square_customer_id
        customer_id = existing_user.id
    
    if not sq_customer_id:
        # Generate basic name if split fails
        full_name = customer_info.get("name", "One Time Customer")
        name_parts = full_name.split(" ", 1)
        given_name = name_parts[0]
        family_name = name_parts[1] if len(name_parts) > 1 else ""
        
        sq_res = create_square_customer(
            given_name=given_name,
            family_name=family_name,
            email=customer_info.get("email")
        )
        if sq_res.get("success"):
            sq_customer_id = sq_res.get("customer_id")
            
            if existing_user:
                existing_user.square_customer_id = sq_customer_id
                db.commit()

    # 2. Process Payment in Square using the cnon directly
    # Reverting to direct nonce charge to match user's curl spec 100%
    idempotency_key = request.idempotency_key or f"otp-{uuid.uuid4().hex}"
    
    logger.info(f"Attempting one-time payment: Amount=${request.total_amount}, Source={request.source_id[:15]}...")
    
    payment_res = process_payment(
        source_id=request.source_id,
        amount=request.total_amount,
        idempotency_key=idempotency_key,
        location_id=None # Let Square handle location if not needed, or pass None to match curl
    )
    
    if "errors" in payment_res:
        error_msg = payment_res['errors'][0].get('detail', 'Unknown error')
        logger.error(f"Square payment fail. Full Response: {payment_res}")
        raise HTTPException(status_code=400, detail=f"Payment failed: {error_msg}")

    payment_data = payment_res.get("payment", {})
    square_payment_id = payment_data.get("id")
    
    # 3. Create OneTimeOrder record
    new_order = OneTimeOrder(
        customer_id=existing_user.id if existing_user else None,
        customer_details=customer_info,
        plan_name=request.plan_details.get("name"),
        plan_cost=request.plan_details.get("price"),
        addons=request.addons,
        custom_description=customer_info.get("custom_description"),
        total_cost=request.total_amount,
        square_payment_id=square_payment_id,
        payment_status="COMPLETED"
    )
    db.add(new_order)
    
    # 4. Also record in the global Payments table for unified billing
    new_payment = Payment(
        customer_id=existing_user.id if existing_user else None,
        amount=request.total_amount,
        status="PAID",
        square_transaction_id=square_payment_id
    )
    db.add(new_payment)
    
    db.commit()
    db.refresh(new_order)
    
    return {
        "success": True,
        "order_id": new_order.id,
        "payment": payment_data
    }

@router.get("/one-time-order/{order_id}/pdf")
def download_one_time_receipt(order_id: int, user: Customer = Depends(get_db_user), db: Session = Depends(get_db)):
    """Generate and download a PDF receipt for a one-time order."""
    from models.subscription import OneTimeOrder
    from utils.pdf_generator import generate_one_time_receipt_pdf
    
    order = db.query(OneTimeOrder).filter(OneTimeOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # Security: Ensure user owns this order (or is admin)
    if order.customer_id and order.customer_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this receipt")
        
    return generate_one_time_receipt_pdf(order)

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

@router.get("/addons/db")
def get_db_addons(db: Session = Depends(get_db)):
    """Fetch all addon variations from local database."""
    addons = db.query(ItemVariation).filter(ItemVariation.item_type == "ADDON").all()
    return {"success": True, "addons": addons}

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
    
    print(f"DEBUG: validate_card called with: {request}")
    
    # If no local customer found, we might be in a guest checkout or first step
    # But usually, we want to link it to a local user.
    
    sq_customer_id = customer.square_customer_id if customer else None
    print(f"DEBUG: Local customer found: {customer}")
    print(f"DEBUG: Existing Square customer ID: {sq_customer_id}")
    
    if not sq_customer_id:
        # Create Square Customer
        given_name = request.given_name or (customer.first_name if customer else "Guest")
        family_name = request.family_name or (customer.last_name if customer else "User")
        email = request.email or (customer.email if customer else f"guest_{uuid.uuid4().hex[:8]}@example.com")
        
        print(f"DEBUG: Creating Square customer for {email}")
        res = create_square_customer(
            given_name=given_name,
            family_name=family_name,
            email=email,
            phone_number=request.phone_number or (customer.phone_number if customer else None)
        )
        print(f"DEBUG: create_square_customer result: {res}")
        
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=f"Square customer creation failed: {res.get('error')}")
        sq_customer_id = res.get("customer_id")
        
        if customer:
            customer.square_customer_id = sq_customer_id
            db.commit()

    # Attach Card
    print(f"DEBUG: Attaching card source_id: {request.source_id} to customer: {sq_customer_id}")
    card_res = create_card_on_file(
        source_id=request.source_id,
        customer_id=sq_customer_id
    )
    print(f"DEBUG: create_card_on_file result: {card_res}")
    
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

@router.get("/my-cards")
def get_my_cards(user: Customer = Depends(get_db_user), db: Session = Depends(get_db)):
    """Fetch saved payment methods for the authenticated customer."""
    if not user.square_customer_id:
        return {"success": True, "cards": []}
    
    # 1. Fetch from local DB
    db_methods = db.query(PaymentMethod).filter(PaymentMethod.customer_id == user.id).all()
    db_card_map = {pm.square_card_id: pm for pm in db_methods}
    
    # 2. Fetch from Square to ensure sync
    sq_res = get_customer_cards(user.square_customer_id)
    sq_cards = sq_res.get("cards", []) if sq_res.get("success") else []
    
    # 3. Merge: Start with Square cards and enrich with DB info if available
    final_cards = []
    sq_card_ids_in_list = set()
    
    for sq_c in sq_cards:
        if not sq_c.get("enabled", True):
            continue
            
        card_id = sq_c.get("id")
        sq_card_ids_in_list.add(card_id)
        
        db_pm = db_card_map.get(card_id)
        
        final_cards.append({
            "id": card_id,
            "last_4": sq_c.get("last_4") or (db_pm.last_4_digits if db_pm else ""),
            "brand": sq_c.get("card_brand") or (db_pm.card_brand if db_pm else "Unknown"),
            "exp_month": sq_c.get("exp_month") or (db_pm.exp_month if db_pm else 0),
            "exp_year": sq_c.get("exp_year") or (db_pm.exp_year if db_pm else 0),
            "is_default": db_pm.is_default if db_pm else False,
            "is_active_in_square": True
        })
    
    # Also add any cards from DB that might not have been in Square response (though unlikely if sq sync is on)
    for card_id, pm in db_card_map.items():
        if card_id not in sq_card_ids_in_list:
            final_cards.append({
                "id": pm.square_card_id,
                "last_4": pm.last_4_digits,
                "brand": pm.card_brand,
                "exp_month": pm.exp_month,
                "exp_year": pm.exp_year,
                "is_default": pm.is_default,
                "is_active_in_square": False
            })
    
    return {
        "success": True,
        "cards": final_cards
    }

@router.post("/save-card")
def save_card(request: SaveCardRequest, user: Customer = Depends(get_db_user), db: Session = Depends(get_db)):
    """
    Save a new payment method for the logged-in customer.
    If they have an active subscription, update it to use this new card.
    """
    if not user.square_customer_id:
        # Should ideally have one by now if they reached dashboard, but let's be safe
        res = create_square_customer(
            given_name=user.first_name,
            family_name=user.last_name,
            email=user.email,
            phone_number=user.phone_number
        )
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=f"Failed to create Square customer: {res.get('error')}")
        user.square_customer_id = res.get("customer_id")
        db.commit()

    # 1. Create Card in Square
    card_res = create_card_on_file(
        source_id=request.source_id,
        customer_id=user.square_customer_id
    )
    
    if not card_res.get("success"):
        raise HTTPException(status_code=400, detail=f"Failed to save card: {card_res.get('error')}")
        
    card_id = card_res.get("card_id")
    
    # 2. Save to Local DB
    # Disable previous default
    db.query(PaymentMethod).filter(PaymentMethod.customer_id == user.id).update({"is_default": False})
    
    new_method = PaymentMethod(
        customer_id=user.id,
        square_card_id=card_id,
        last_4_digits=card_res.get("last_4"),
        card_brand=card_res.get("brand"),
        exp_month=card_res.get("exp_month"),
        exp_year=card_res.get("exp_year"),
        is_default=True
    )
    db.add(new_method)
    
    # 3. Update active subscription if exists
    subscription_updated = False
    if user.square_subscription_id and user.subscription_active:
        logger.info(f"Updating subscription {user.square_subscription_id} to use new card {card_id}")
        update_subscription_card(user.square_subscription_id, card_id)
    
    db.commit()
    
    return {
        "success": True,
        "message": "Payment method saved successfully",
        "card_id": card_id
    }

@router.delete("/remove-card/{card_id}")
def remove_card(card_id: str, user: Customer = Depends(get_db_user), db: Session = Depends(get_db)):
    """Disable a card in Square and remove from local DB."""
    # 1. Disable in Square
    sq_res = disable_card(card_id)
    
    # 2. Remove from Local DB (or mark as inactive)
    method = db.query(PaymentMethod).filter(
        PaymentMethod.customer_id == user.id,
        PaymentMethod.square_card_id == card_id
    ).first()
    
    if method:
        db.delete(method)
        db.commit()
        
    return {"success": True, "message": "Card removed successfully"}

def dummy_create_subscription(customer_id: str, location_id: str, plan_variation_id: str, card_id: str, **kwargs) -> Dict[str, Any]:
    """Helper for testing to skip real Square call"""
    return {
        "success": True,
        "subscription_id": f"dummy_sub_{uuid.uuid4().hex[:12]}",
        "subscription": {"status": "ACTIVE"}
    }

@router.post("/activate-subscription")
def activate_sub(request: ActivateSubscriptionRequest, db: Session = Depends(get_db)):
    from models.subscription import ItemVariation, SubscriptionPlan
    from utils.square_client import create_order, get_catalog_prices, create_subscription as create_sq_sub
    
    customer = None
    if request.customer_id:
        customer = db.query(Customer).get(request.customer_id)
    
    sq_customer_id = customer.square_customer_id if customer else None
    if not sq_customer_id:
        raise HTTPException(status_code=400, detail="Square customer ID missing")

    location_id = request.location_id or os.getenv("SQUARE_LOCATION_ID")
    
    # 1. Prepare Order Template (Line Items)
    from utils.subscription_logic import prepare_subscription_order_items
    order_data = prepare_subscription_order_items(db, request.plan_variation_id, request.addons)
    if not order_data.get("success"):
        raise HTTPException(status_code=400, detail=order_data.get("error"))

    subtotal = order_data["subtotal"]
    processing_fee = order_data["processing_fee"]

    # 4. Create Order Template
    order_res = create_order(
        location_id=location_id,
        line_items=order_data["line_items"],
        idempotency_key=f"order-{request.idempotency_key or uuid.uuid4().hex}"
    )
    
    if not order_res.get("success"):
        raise HTTPException(status_code=400, detail=f"Order template creation failed: {order_res.get('error')}")
    
    order_id = order_res.get("order_id")
    
    # 5. Create Subscription
    res = create_sq_sub(
        customer_id=sq_customer_id,
        location_id=location_id,
        plan_variation_id=request.plan_variation_id,
        card_id=request.card_id,
        idempotency_key=request.idempotency_key,
        start_date=request.start_date,
        order_template_id=order_id
    )
    
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=f"Subscription failed: {res.get('error')}")

    if customer:
        customer.square_subscription_id = res.get("subscription_id")
        customer.order_template_id = order_id # Store the order template ID
        customer.subscription_active = True
        customer.subscription_status = "ACTIVE"
        customer.selected_addons = request.addons
        db.commit()
        
        # Log payment locally
        # Log the full amount including addons and fee
        total_amount = subtotal + processing_fee
        new_payment = Payment(
            customer_id=customer.id,
            amount=total_amount,
            status="PAID",
            square_transaction_id=res.get("subscription_id")
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
def get_my_subs(user: Customer = Depends(get_db_user), db: Session = Depends(get_db)):
    if not user.square_customer_id:
        return {"success": True, "subscriptions": []}
    
    # Fetch user's subscriptions from Square
    subs_res = get_subscriptions(customer_id=user.square_customer_id)
    if not subs_res.get("success"):
        return subs_res
        
    subscriptions = subs_res.get("subscriptions", [])
    
    # FETCH FROM LOCAL DB - MUCH FASTER
    plans = db.query(SubscriptionPlan).all()
    plans_map = {}
    for p in plans:
        plans_map[p.plan_variation_id] = {
            "name": p.plan_name,
            "amount": int(p.plan_cost * 100)
        }
    
    # Enrich subscriptions
    enriched_subs = []
    for sub in subscriptions:
        s = sub.copy()
        var_id = s.get("plan_variation_id")
        
        if var_id in plans_map:
            s["plan_name"] = plans_map[var_id]["name"]
            s["amount"] = plans_map[var_id]["amount"]
        else:
            s["plan_name"] = "Unknown Plan"
            s["amount"] = 0
            
        s["next_billing_date"] = s.get("charged_through_date")
        s["selected_addons"] = user.selected_addons
        enriched_subs.append(s)
        
    return {"success": True, "subscriptions": enriched_subs}

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
def billing_history(user: Customer = Depends(get_db_user), db: Session = Depends(get_db)):
    """Fetch billing history from local records first, then Square."""
    from models.subscription import Invoice
    
    # 1. Start with local invoices (subscriptions)
    local_invoices = db.query(Invoice).filter(Invoice.customer_id == user.id).order_by(Invoice.due_date.desc()).all()
    
    from models.subscription import OneTimeOrder
    one_time_orders = db.query(OneTimeOrder).filter(OneTimeOrder.customer_id == user.id).order_by(OneTimeOrder.created_at.desc()).all()
    
    bill_history = []
    
    # Add subscription invoices
    for inv in local_invoices:
        bill_history.append({
            "id": inv.square_invoice_id,
            "amount": int(inv.amount * 100),
            "status": inv.status,
            "created_at": inv.due_date.isoformat(),
            "description": "Subscription Payment",
            "public_url": inv.public_url,
            "type": "SUBSCRIPTION",
            "skeeterman": user.skeeterman_number,
            "customer_name": f"{user.first_name} {user.last_name}",
            "phone": user.phone_number
        })
        
    # Add one-time orders
    for order in one_time_orders:
        desc = f"One-Time Service: {order.plan_name}"
        if order.plan_name == "Custom Service" and order.custom_description:
             desc = f"Custom Service: {order.custom_description}"

        bill_history.append({
            "id": f"OTP-{order.id}",
            "amount": int(order.total_cost * 100),
            "status": order.payment_status,
            "created_at": order.created_at.isoformat(),
            "description": desc,
            "public_url": f"/payments/one-time-order/{order.id}/pdf", # Local PDF download link
            "type": "ONE_TIME",
            "skeeterman": user.skeeterman_number,
            "customer_name": f"{user.first_name} {user.last_name}",
            "phone": user.phone_number
        })
        
    if bill_history:
        # Sort combined history by date descending
        bill_history.sort(key=lambda x: x["created_at"], reverse=True)
        return {
            "success": True, 
            "invoices": bill_history
        }

    # 2. Fallback to Square if no local records found
    if not user.square_customer_id:
        return {"success": True, "invoices": []}
    
    res = get_customer_invoices(user.square_customer_id)
    if not res.get("success"):
        return res
        
    invoices = res.get("invoices", [])
    enriched_invoices = []
    for inv in invoices:
        i = inv.copy()
        amount = 0
        if "payment_requests" in i and i["payment_requests"]:
            for req in i["payment_requests"]:
                 amount += int(req.get("computed_amount_money", {}).get("amount", 0))
        
        i["amount"] = amount
        i["description"] = i.get("title") or i.get("description") or "Subscription Payment"
        i["created_at"] = i.get("invoice_date") or i.get("scheduled_at") or i.get("created_at")
        enriched_invoices.append(i)
        
    return {"success": True, "invoices": enriched_invoices}

@router.get("/dashboard-data")
def get_dashboard_data(user: Customer = Depends(get_db_user), db: Session = Depends(get_db)):
    """Unified endpoint for faster dashboard loading."""
    # This combines multiple calls into one to reduce latency and overhead
    try:
        subs = get_my_subs(user, db)
        history = billing_history(user, db)
        plans = get_db_plans(db)
        addons = get_db_addons(db)
        
        return {
            "success": True,
            "subscriptions": subs.get("subscriptions", []),
            "billing_history": history.get("invoices", []),
            "available_plans": plans.get("plans", []),
            "available_addons": addons.get("addons", []),
            "failed_attempts": user.failed_payment_attempts,
            "status": user.subscription_status
        }
    except Exception as e:
        logger.error(f"Error fetching dashboard data: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard data.")
@router.get("/my-invoice-pdf/{square_invoice_id}")
def download_my_invoice_pdf(
    square_invoice_id: str,
    db: Session = Depends(get_db),
    user: Customer = Depends(get_db_user)
):
    from models.subscription import Invoice, SubscriptionPlan
    from utils.pdf_generator import generate_invoice_pdf
    
    invoice = db.query(Invoice).filter(Invoice.square_invoice_id == square_invoice_id).first()
    if not invoice:
        # If not in local DB, it might be in Square.
        # For simplicity, we expect sync or we can fetch details from Square here.
        # But let's check local first.
        raise HTTPException(status_code=404, detail="Invoice not found. If this is a new payment, please wait a moment.")
        
    if invoice.customer_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this invoice.")
        
    # Get plan name
    plan_name = "Subscription Service"
    if user.plan_id:
        try:
            plan = db.query(SubscriptionPlan).get(int(user.plan_id))
            if plan:
                plan_name = plan.plan_name
        except:
            pass
            
    return generate_invoice_pdf(invoice, user, plan_name)
