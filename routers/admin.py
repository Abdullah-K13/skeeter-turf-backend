from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
import os
import tempfile
from fpdf import FPDF
from datetime import datetime, date, timedelta
from pydantic import BaseModel

from db.init import get_db
from models.user import Customer, Admin
from models.subscription import SubscriptionPlan, SubscriptionLog, Invoice, Payment, PaymentMethod
from utils.deps import get_current_user

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
    skeeterman_number: str


class PlanDistributionItem(BaseModel):
    name: str
    value: int
    color: str

class GrowthItem(BaseModel):
    date: str
    customers: int

class AnalyticsResponse(BaseModel):
    mrr: float
    active_subscribers: int
    total_customers: int
    plan_distribution: List[PlanDistributionItem]
    revenue_distribution: List[PlanDistributionItem]
    growth_history: List[GrowthItem]

@router.get("/stats")
def get_admin_stats(
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # We can reuse the logic or just return basic stats.
    # For now, let's return the active subscriber count from Square.
    from utils.square_client import search_subscriptions
    subs_res = search_subscriptions(status="ACTIVE")
    active_subs = subs_res.get("subscriptions", [])
    
    return {
        "active_subscribers": len(active_subs)
    }

@router.get("/analytics", response_model=AnalyticsResponse)
def get_admin_analytics(
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # 1. Active Subscribers & MRR & Plan Distribution via Square API
    from utils.square_client import search_subscriptions, get_subscription_plans
    
    # Fetch all active subscriptions from Square
    subs_res = search_subscriptions(status="ACTIVE")
    active_subs = subs_res.get("subscriptions", [])
    active_sub_count = len(active_subs)
    
    # Fetch plan details to calculate MRR
    plans_res = get_subscription_plans()
    plans = plans_res.get("plans", [])
    
    # Create a map of variation_id -> price & name
    # We need to flatten the structure: plan -> variations
    variation_map = {}
    for p in plans:
        p_name = p.get("name", "Unknown Plan")
        for v in p.get("variations", []):
            var_id = v.get("id")
            # Price is likely inside phases -> recurring_price_money -> amount
            # Square structure can be complex. Let's try to find the price.
            # Simplified assumption: first phase has the recurring price.
            phases = v.get("phases", [])
            price = 0.0
            if phases:
                amount_money = phases[0].get("recurring_price_money", {})
                price = float(amount_money.get("amount", 0)) / 100.0
            
            variation_map[var_id] = {"name": p_name, "price": price}

    mrr = 0.0
    plan_counts = {} # plan_name -> count
    plan_revenue = {} # plan_name -> total_revenue
    
    for sub in active_subs:
        var_id = sub.get("plan_variation_id")
        if var_id and var_id in variation_map:
            details = variation_map[var_id]
            price = details["price"]
            p_name = details["name"]
            
            mrr += price
            plan_counts[p_name] = plan_counts.get(p_name, 0) + 1
            plan_revenue[p_name] = plan_revenue.get(p_name, 0) + price
        else:
            # Fallback if plan not found in catalog but exists in sub
            p_name = "Unknown Plan"
            plan_counts[p_name] = plan_counts.get(p_name, 0) + 1
            plan_revenue[p_name] = plan_revenue.get(p_name, 0) + 0.0

    # Format Plan Distribution & Revenue Distribution
    colors = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6"]
    plan_dist = []
    rev_dist = []
    
    for i, name in enumerate(plan_counts.keys()):
        color = colors[i % len(colors)]
        
        plan_dist.append(PlanDistributionItem(
            name=name,
            value=plan_counts[name],
            color=color
        ))
        
        rev_dist.append(PlanDistributionItem(
            name=name,
            value=int(plan_revenue.get(name, 0)), # Cast to int for graph if needed, or keep and update model
            color=color
        ))
        
    # 2. Total Customers (Local DB - historically accurate for platform users)
    total_customers = db.query(Customer).count()
    
    # 3. Growth History (Last 30 days - Local DB)
    from sqlalchemy import func
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    daily_growth = db.query(
        func.date(Customer.created_at).label('date'),
        func.count(Customer.id)
    ).filter(Customer.created_at >= thirty_days_ago)\
     .group_by(func.date(Customer.created_at))\
     .order_by(func.date(Customer.created_at))\
     .all()
     
    growth_map = {str(d): c for d, c in daily_growth}
    
    growth_history = []
    # Get count before 30 days
    count_before = db.query(Customer).filter(Customer.created_at < thirty_days_ago).count()
    current_total = count_before
    
    for i in range(31):
        d = thirty_days_ago + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        daily_new = growth_map.get(d_str, 0)
        current_total += daily_new
        growth_history.append(GrowthItem(date=d_str, customers=current_total))

    # Debug logs
    print(f"DEBUG: Square Active Subs: {active_sub_count}")
    print(f"DEBUG: Square MRR: {mrr}")
    print(f"DEBUG: Plan Distribution: {plan_counts}")

    return AnalyticsResponse(
        mrr=mrr,
        active_subscribers=active_sub_count,
        total_customers=total_customers,
        plan_distribution=plan_dist,
        revenue_distribution=rev_dist,
        growth_history=growth_history
    )

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
            status=c.subscription_status.capitalize() if c.subscription_status else ("Active" if c.subscription_active else "Inactive"),
            amount=plan_cost,
            lastPayment=last_payment_str,
            address=c.address or "",
            city=c.city or "",
            zip=c.zip_code or "",
            skeeterman_number=c.skeeterman_number or ""
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
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if not customer.square_customer_id:
        return {"success": True, "cards": []}
    
    # 1. Fetch from local DB
    db_methods = db.query(PaymentMethod).filter(PaymentMethod.customer_id == customer.id).all()
    db_card_map = {pm.square_card_id: pm for pm in db_methods}
    
    # 2. Fetch from Square
    from utils.square_client import get_customer_cards as get_sq_cards
    sq_res = get_sq_cards(customer.square_customer_id)
    sq_cards = sq_res.get("cards", []) if sq_res.get("success") else []
    
    # 3. Merge and format for frontend
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
    
    # Add any cards from DB not in Square response
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
    
    return {"success": True, "cards": final_cards}

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
    
    # Remove from Local DB
    db.query(PaymentMethod).filter(
        PaymentMethod.customer_id == customer_id,
        PaymentMethod.square_card_id == card_id
    ).delete()
    db.commit()
    
    return {"success": True, "message": "Card removed"}

class AddCardRequest(BaseModel):
    source_id: str

@router.post("/save-card/{customer_id}")
def admin_save_card(
    customer_id: int,
    request: AddCardRequest,
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    customer = db.query(Customer).get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Ensure Square Customer exists
    if not customer.square_customer_id:
        from utils.square_client import create_square_customer
        res = create_square_customer(
            given_name=customer.first_name,
            family_name=customer.last_name,
            email=customer.email,
            phone_number=customer.phone_number
        )
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=f"Square customer error: {res.get('error')}")
        customer.square_customer_id = res.get("customer_id")
        db.commit()

    # Create Card in Square
    from utils.square_client import create_card_on_file
    card_res = create_card_on_file(
        source_id=request.source_id,
        customer_id=customer.square_customer_id
    )
    
    if not card_res.get("success"):
        raise HTTPException(status_code=400, detail=f"Failed to save card: {card_res.get('error')}")
        
    card_id = card_res.get("card_id")
    
    # Save to Local DB
    # Disable previous default
    db.query(PaymentMethod).filter(PaymentMethod.customer_id == customer.id).update({"is_default": False})
    
    new_method = PaymentMethod(
        customer_id=customer.id,
        square_card_id=card_id,
        last_4_digits=card_res.get("last_4"),
        card_brand=card_res.get("brand"),
        exp_month=card_res.get("exp_month"),
        exp_year=card_res.get("exp_year"),
        is_default=True
    )
    db.add(new_method)
    
    # Update active subscription if exists
    if customer.square_subscription_id and customer.subscription_active:
        from utils.square_client import update_subscription_card
        update_subscription_card(customer.square_subscription_id, card_id)
    
    db.commit()
    return {"success": True, "message": "Card saved successfully"}

class UpdateCustomerRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone_number: str
    address: str
    city: str
    zip_code: str
    skeeterman_number: str

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
    customer.skeeterman_number = request.skeeterman_number
    
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

class ChangeSubscriptionRequest(BaseModel):
    new_plan_variation_id: str

@router.post("/change-subscription/{customer_id}")
def admin_change_subscription(
    customer_id: int,
    request: ChangeSubscriptionRequest,
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    customer = db.query(Customer).get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    if not customer.square_subscription_id:
        raise HTTPException(status_code=400, detail="Customer has no active subscription")
    
    from utils.square_client import update_subscription
    res = update_subscription(customer.square_subscription_id, request.new_plan_variation_id)
    
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=f"Square error: {res.get('error')}")
        
    # Update local DB if necessary? 
    # Usually Square webhook or next sync updates it, but we can try to update plan_id if we know it.
    # We can try to find the plan by variation_id
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_variation_id == request.new_plan_variation_id).first()
    if plan:
        customer.plan_id = str(plan.id)
        customer.plan_variation_id = request.new_plan_variation_id
        db.commit()
    
    return {"success": True, "message": "Subscription updated successfully"}
@router.post("/sync-invoices/{customer_id}")
def sync_customer_invoices(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    customer = db.query(Customer).get(customer_id)
    if not customer or not customer.square_customer_id:
        raise HTTPException(status_code=404, detail="Customer not found or no Square ID")
    
    from utils.square_client import search_invoices
    res = search_invoices(customer.square_customer_id)
    
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=f"Square error: {res.get('error')}")
    
    sq_invoices = res.get("invoices", [])
    synced_count = 0
    
    for sq_inv in sq_invoices:
        inv_id = sq_inv.get("id")
        
        # Robust amount extraction
        amount_data = {}
        if sq_inv.get("payment_requests"):
            amount_data = sq_inv.get("payment_requests")[0].get("computed_amount_money", {})
        if not amount_data.get("amount") and sq_inv.get("next_payment_amount_money"):
             amount_data = sq_inv.get("next_payment_amount_money")
             
        amount = float(amount_data.get("amount", 0)) / 100.0
        
        # Check if already exists
        existing = db.query(Invoice).filter(Invoice.square_invoice_id == inv_id).first()
        
        # Date parsing
        due_date_str = sq_inv.get("scheduled_at") or sq_inv.get("created_at", datetime.now().isoformat())
        try:
            # Square dates can be ISO formats
            if "T" in due_date_str:
                due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00")).date()
            else:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except:
            due_date = datetime.now().date()

        if not existing:
            new_inv = Invoice(
                square_invoice_id=inv_id,
                customer_id=customer.id,
                subscription_id=sq_inv.get("subscription_id"),
                amount=amount,
                status=sq_inv.get("status"),
                due_date=due_date,
                public_url=sq_inv.get("public_url")
            )
            db.add(new_inv)
            synced_count += 1
        else:
            # Update status and URL if changed
            existing.status = sq_inv.get("status")
            existing.public_url = sq_inv.get("public_url")
            existing.amount = amount # Keep amount updated too
    
    db.commit()
    return {"success": True, "synced": synced_count}

@router.get("/invoice-pdf/{square_invoice_id}")
def download_invoice_pdf(
    square_invoice_id: str,
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
        
    invoice = db.query(Invoice).filter(Invoice.square_invoice_id == square_invoice_id).first()
    if not invoice:
        # Try to sync first? Or just error. 
        # Better to error and expect sync happened.
        raise HTTPException(status_code=404, detail="Invoice not found in local records. Please sync first.")
        
    customer = db.query(Customer).get(invoice.customer_id)
    
    # Get plan name
    plan_name = "Subscription Service"
    if customer.plan_id:
        try:
            plan = db.query(SubscriptionPlan).get(int(customer.plan_id))
            if plan:
                plan_name = plan.plan_name
        except:
            pass
            
    from utils.pdf_generator import generate_invoice_pdf
    return generate_invoice_pdf(invoice, customer, plan_name)
