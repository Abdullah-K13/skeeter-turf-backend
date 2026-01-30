from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
import os
import uuid
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
    selected_addons: Optional[List[str]] = None
    plan_variation_id: Optional[str] = None
    addons_list: Optional[List[dict]] = None


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
    
    # Imports for local calculation
    from models.subscription import SubscriptionPlan, ItemVariation
    from models.user import Customer
    
    # 1. Fetch Necessary Data
    # Get all potential recurring plans
    all_plans = db.query(SubscriptionPlan).all()
    # Map variation_id -> Plan Object
    plan_map = {p.plan_variation_id: p for p in all_plans if p.plan_variation_id}
    # Map plan_id (str(id)) -> Plan Object (fallback if variation_id missing on customer but plan_id present)
    plan_id_map = {str(p.id): p for p in all_plans}

    # Get all addons to calculate Addon Revenue
    all_addons = db.query(ItemVariation).filter(ItemVariation.item_type == "ADDON").all()
    addon_map = {a.variation_id: a for a in all_addons}

    # active_subscribers_query
    active_customers = db.query(Customer).filter(
        Customer.subscription_active == True,
        Customer.subscription_status == "ACTIVE" 
    ).all()

    active_sub_count = len(active_customers)
    
    # 2. Calculate MRR & Distributions
    mrr = 0.0
    plan_counts = {p.plan_name: 0 for p in all_plans}
    plan_revenue = {p.plan_name: 0.0 for p in all_plans}
    
    # Initialize "Unknown" or "Custom" if needed, but let's stick to defined plans primarily
    
    for customer in active_customers:
        # Determine Base Plan Cost
        customer_plan_cost = 0.0
        plan_name = "Unknown Plan"
        
        # Try finding plan by variation ID first
        if customer.plan_variation_id and customer.plan_variation_id in plan_map:
            plan = plan_map[customer.plan_variation_id]
            customer_plan_cost = plan.plan_cost
            plan_name = plan.plan_name
        # Fallback to plan_id look up
        elif customer.plan_id and customer.plan_id in plan_id_map:
            plan = plan_id_map[customer.plan_id]
            customer_plan_cost = plan.plan_cost
            plan_name = plan.plan_name
            
        # Determine Addons Cost
        addons_cost = 0.0
        if customer.selected_addons:
            for addon_id in customer.selected_addons:
                if addon_id in addon_map:
                    addons_cost += addon_map[addon_id].price
        
        total_customer_revenue = customer_plan_cost + addons_cost
        
        # Aggregate
        mrr += total_customer_revenue
        
        # Add to distributions (create key if not exists, though we init'd above)
        if plan_name not in plan_counts:
            plan_counts[plan_name] = 0
            plan_revenue[plan_name] = 0.0
            
        plan_counts[plan_name] += 1
        plan_revenue[plan_name] += total_customer_revenue

    # Format Plan Distribution & Revenue Distribution
    colors = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", "#6366f1", "#ec4899"]
    plan_dist = []
    rev_dist = []
    
    # Sort by value or name? Let's sort by name for consistency
    sorted_plans = sorted(plan_counts.keys())
    
    for i, name in enumerate(sorted_plans):
        # Skip if 0? Maybe keep to show 0 if it's a valid plan
        # Let's skip 0 to keep chart clean
        if plan_counts[name] == 0:
            continue

        color = colors[i % len(colors)]
        
        plan_dist.append(PlanDistributionItem(
            name=name,
            value=plan_counts[name],
            color=color
        ))
        
        rev_dist.append(PlanDistributionItem(
            name=name,
            value=int(plan_revenue.get(name, 0)),
            color=color
        ))
        
    # 3. Total Customers (Local DB - Existing Logic)
    total_customers = db.query(Customer).count()
    
    # 4. Growth History (Last 30 days - Local DB - Existing Logic)
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
    print(f"DEBUG: Active Subs (Local): {active_sub_count}")
    print(f"DEBUG: MRR (Local): {mrr}")

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
    
    from models.subscription import Payment, OneTimeOrder
    
    # Optimized fetch: get all customers, plans, and last payments in bulk
    customers = db.query(Customer).all()
    all_plans = {p.id: p for p in db.query(SubscriptionPlan).all()}
    
    # helper for addons
    from utils.square_client import get_catalog_prices
    # We ideally should have a local cache of addons, but for now lets fetch DB versions if we synced them
    # But since addons are dynamic in Square, we might just assume we have names if we synced.
    # To be safe, let's just use what we have in `selected_addons`.
    # We will need prices though.
    
    # Let's just fetch all subscription plans from DB which might have addon info if we synced them?
    # No, typically addons are separate. 
    # For this listing, if we want detailed addon info (name + price), we need to fetch catalog.
    # That might be slow for ALOT of customers. 
    # Optimization: Fetch all addons once.
    from models.subscription import ItemVariation
    all_addons = {a.variation_id: a for a in db.query(ItemVariation).filter(ItemVariation.item_type == "ADDON").all()}

    # Get all last payments in one query
    last_payments = db.query(
        Payment.customer_id,
        func.max(Payment.created_at)
    ).group_by(Payment.customer_id).all()
    last_payment_map = {cid: dt for cid, dt in last_payments}

    result = []
    for c in customers:
        plan_display = "No Plan"
        total_monthly_amount = 0.0
        details_addons = []

        # 1. Base Plan Logic
        try:
            if c.plan_id == "one-time":
                # Check for the latest one-time order to distinguish "One-Time" vs "Custom Service"
                latest_order = db.query(OneTimeOrder).filter(OneTimeOrder.customer_id == c.id).order_by(OneTimeOrder.created_at.desc()).first()
                if latest_order:
                     if latest_order.plan_name == "Custom Service":
                         plan_display = "Custom Service"
                     else:
                         plan_display = latest_order.plan_name or "One-Time Service"
                else:
                    plan_display = "One-Time Service"
                
                total_monthly_amount = 0.0 
            else:
                pid = int(c.plan_id) if c.plan_id else None
                if pid and pid in all_plans:
                    base_plan = all_plans[pid]
                    plan_display = base_plan.plan_name
                    total_monthly_amount += base_plan.plan_cost
                elif c.plan_id:
                     # Fallback if plan ID exists but not in DB (maybe deleted local plan)
                     plan_display = "Unknown Plan"
        except (ValueError, TypeError):
            pass

        # 2. Addons Logic
        if c.selected_addons:
             for addon_id in c.selected_addons:
                 if addon_id in all_addons:
                     addon = all_addons[addon_id]
                     total_monthly_amount += addon.price
                     details_addons.append({"name": addon.name, "price": addon.price})
                 else:
                     details_addons.append({"name": "Unknown Addon", "price": 0.0})

        # 3. Custom/One-Time Order Check
        # If they also have custom one-time orders, we might want to flag that.
        # But usually "One-Time" plan users are just that.
        # If a subscriber ALSO ordered a custom service, they are still a subscriber.
        
        # Refine Plan Display for UI
        if c.selected_addons and len(c.selected_addons) > 0:
            plan_display += f" + {len(c.selected_addons)} Addon(s)"

        last_payment_date = last_payment_map.get(c.id)
        last_payment_str = last_payment_date.strftime("%Y-%m-%d") if last_payment_date else "N/A"

        result.append(CustomerListItem(
            id=c.id,
            name=f"{c.first_name} {c.last_name}",
            email=c.email,
            phone=c.phone_number or "",
            plan=plan_display,
            status=c.subscription_status.capitalize() if c.subscription_status else ("Active" if c.subscription_active else "Inactive"),
            amount=round(total_monthly_amount, 2),
            lastPayment=last_payment_str,
            address=c.address or "",
            city=c.city or "",
            zip=c.zip_code or "",
            skeeterman_number=c.skeeterman_number or "",
            selected_addons=c.selected_addons,
            plan_variation_id=c.plan_variation_id,
            addons_list=details_addons
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
    addons: Optional[List[str]] = None

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

    from utils.subscription_logic import prepare_subscription_order_items
    from utils.square_client import create_order, update_subscription, create_subscription, get_catalog_prices
    
    # 1. Fetch and Filter Addons
    recurring_addon_ids = []
    one_time_addons = []
    
    from models.subscription import ItemVariation, OneTimeOrder, Payment
    
    if request.addons:
        db_addons = db.query(ItemVariation).filter(
            ItemVariation.variation_id.in_(request.addons)
        ).all()
        
        for addon in db_addons:
            if addon.billing_type == "ONE_TIME":
                one_time_addons.append(addon)
            else:
                recurring_addon_ids.append(addon.variation_id)

    # 2. Process One-Time Addons Immediate Charge
    if one_time_addons:
        # Check for default card
        default_card = db.query(PaymentMethod).filter(
            PaymentMethod.customer_id == customer.id,
            PaymentMethod.is_default == True
        ).first()
        
        if not default_card:
            raise HTTPException(status_code=400, detail="Customer has no default payment method. Please add a card to process one-time addons.")
            
        # Calculate total for one-time items
        ot_subtotal = sum(a.price for a in one_time_addons)
        ot_processing_fee = (ot_subtotal * 0.040) + 0.10
        ot_final_amount = ot_subtotal + ot_processing_fee
        
        # Charge the card on file
        from utils.square_client import process_payment
        
        pay_res = process_payment(
            source_id=default_card.square_card_id,
            amount=ot_final_amount,
            idempotency_key=f"admin-ot-{uuid.uuid4().hex}",
            customer_id=customer.square_customer_id,
            location_id=os.getenv("SQUARE_LOCATION_ID")
        )
        
        if "errors" in pay_res:
             err_detail = pay_res['errors'][0].get('detail', 'One-time payment failed')
             raise HTTPException(status_code=400, detail=f"Failed to charge one-time addons: {err_detail}")
             
        # Record OneTimeOrder
        new_order = OneTimeOrder(
            customer_id=customer.id,
            customer_details={
                "email": customer.email,
                "name": f"{customer.first_name} {customer.last_name}"
            },
            plan_name="Admin Added One-Time Addons",
            plan_cost=ot_subtotal,
            addons=[{"name": a.name, "price": a.price, "billing_type": a.billing_type} for a in one_time_addons],
            total_cost=ot_final_amount,
            square_payment_id=pay_res.get("payment", {}).get("id"),
            payment_status="COMPLETED"
        )
        db.add(new_order)
        
        # Record Payment
        new_payment = Payment(
            customer_id=customer.id,
            amount=ot_final_amount,
            status="PAID",
            square_transaction_id=pay_res.get("payment", {}).get("id")
        )
        db.add(new_payment)
        db.commit()

    # 3. Prepare Subscription Order Template (Recurring items only)
    # We use ONLY recurring_addon_ids here
    order_data = prepare_subscription_order_items(db, request.new_plan_variation_id, recurring_addon_ids)
    if not order_data.get("success"):
        raise HTTPException(status_code=400, detail=order_data.get("error"))

    location_id = os.getenv("SQUARE_LOCATION_ID")
    order_res = create_order(
        location_id=location_id,
        line_items=order_data["line_items"],
        idempotency_key=f"admin-upd-order-{uuid.uuid4().hex}"
    )
    if not order_res.get("success"):
        raise HTTPException(status_code=400, detail=f"Failed to create order template: {order_res.get('error')}")
    
    order_id = order_res.get("order_id")

    # 4. Update or Create Subscription
    if customer.square_subscription_id:
        # EXISTING SUBSCRIPTION -> UPDATE
        res = update_subscription(
            subscription_id=customer.square_subscription_id,
            plan_variation_id=request.new_plan_variation_id,
            order_template_id=order_id
        )
        action = "CHANGE_PLAN"
    else:
        # NO SUBSCRIPTION -> CREATE (One-time to Subscription conversion)
        # Check for card again if not checked above
        default_card = db.query(PaymentMethod).filter(
            PaymentMethod.customer_id == customer.id,
            PaymentMethod.is_default == True
        ).first()

        if not default_card:
            raise HTTPException(status_code=400, detail="No saved payment method found for this customer. Please add a card first.")

        res = create_subscription(
            customer_id=customer.square_customer_id,
            location_id=location_id,
            plan_variation_id=request.new_plan_variation_id,
            card_id=default_card.square_card_id,
            order_template_id=order_id,
            idempotency_key=f"admin-activ-{uuid.uuid4().hex}"
        )
        action = "ACTIVATE"
    
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=f"Square error: {res.get('error')}")
        
    # 5. Update local DB
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_variation_id == request.new_plan_variation_id).first()
    if plan:
        customer.plan_id = str(plan.id)
        customer.plan_variation_id = request.new_plan_variation_id
        customer.selected_addons = request.addons # We store ALL addons selected (even if one-time processed) for record, or maybe just recurring?
        # Typically selected_addons in customer profile implies ACTIVE recurring addons.
        # One-time addons should probably NOT be stored in selected_addons permanently if they are just one-time.
        # Let's ONLY store recurring_addon_ids in the customer profile so they show up as active.
        customer.selected_addons = recurring_addon_ids 
        customer.order_template_id = order_id
        
        if not customer.square_subscription_id:
            customer.square_subscription_id = res.get("subscription_id")
            customer.subscription_active = True
            customer.subscription_status = "ACTIVE"
            
        # Log action
        log = SubscriptionLog(
            customer_id=customer.id,
            subscription_id=customer.square_subscription_id,
            action=action,
            effective_date=date.today()
        )
        db.add(log)
        db.commit()
    
    return {"success": True, "message": "Subscription updated successfully", "action": action}
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

@router.post("/resume-subscription/{customer_id}")
def resume_customer_subscription(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    customer = db.query(Customer).get(customer_id)
    if not customer or not customer.square_subscription_id:
        raise HTTPException(status_code=404, detail="Active subscription not found")

    from utils.square_client import resume_subscription
    res = resume_subscription(customer.square_subscription_id)

    if "errors" in res:
        raise HTTPException(status_code=400, detail=str(res["errors"]))

    customer.subscription_status = "ACTIVE"
    customer.subscription_active = True
    
    log = SubscriptionLog(
        customer_id=customer.id,
        subscription_id=customer.square_subscription_id,
        action="RESUME_ADMIN",
        effective_date=date.today()
    )
    db.add(log)
    db.commit()
    
    return {"success": True, "message": "Subscription resumed"}

@router.post("/pause-subscription/{customer_id}")
def pause_customer_subscription(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    customer = db.query(Customer).get(customer_id)
    if not customer or not customer.square_subscription_id:
        raise HTTPException(status_code=404, detail="Active subscription not found")

    from utils.square_client import pause_subscription
    res = pause_subscription(customer.square_subscription_id)

    if "errors" in res:
        raise HTTPException(status_code=400, detail=str(res["errors"]))

    customer.subscription_status = "PAUSED"
    # We might keep subscription_active = True technically, as it's not canceled.
    
    log = SubscriptionLog(
        customer_id=customer.id,
        subscription_id=customer.square_subscription_id,
        action="PAUSE_ADMIN",
        effective_date=date.today()
    )
    db.add(log)
    db.commit()
    
    return {"success": True, "message": "Subscription paused"}

@router.post("/activate-subscription/{customer_id}")
def activate_stored_subscription(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: Admin = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    customer = db.query(Customer).get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    if customer.subscription_active and customer.subscription_status == "ACTIVE":
         raise HTTPException(status_code=400, detail="Customer is already active")

    # Check for required data
    if not customer.plan_variation_id:
        raise HTTPException(status_code=400, detail="Customer has no plan selected. Please use Change Subscription.")
        
    if not customer.square_customer_id:
        raise HTTPException(status_code=400, detail="Customer has no Square profile. Please add payment method first.")

    # Find default card
    default_card = db.query(PaymentMethod).filter(
        PaymentMethod.customer_id == customer.id,
        PaymentMethod.is_default == True
    ).first()

    if not default_card:
        # Try to find any card
        default_card = db.query(PaymentMethod).filter(
            PaymentMethod.customer_id == customer.id
        ).first()
        
    if not default_card:
        raise HTTPException(status_code=400, detail="No payment method on file. Please add a card first.")

    # Prepare logic similar to other activation
    from utils.square_client import create_order, create_subscription
    from utils.subscription_logic import prepare_subscription_order_items
    
    # 1. Prepare Order
    # We use currently selected addons if they are recurring? 
    # Or just use empty addons list and let admin add them later?
    # Let's assume we want to reactivate what they had designated in selected_addons if possible
    # But selected_addons might be stale. Best to activate base plan and let admin add addons.
    # actually, if we use what is in `selected_addons` (list of IDs), we might be safer.
    
    # Let's try to use valid recurring addons from their profile
    recurring_addon_ids = []
    if customer.selected_addons:
        from models.subscription import ItemVariation
        # Validate they exist and are recurring
        valid_addons = db.query(ItemVariation).filter(
            ItemVariation.variation_id.in_(customer.selected_addons),
            ItemVariation.billing_type != "ONE_TIME"
        ).all()
        recurring_addon_ids = [a.variation_id for a in valid_addons]

    order_data = prepare_subscription_order_items(db, customer.plan_variation_id, recurring_addon_ids)
    if not order_data.get("success"):
        raise HTTPException(status_code=400, detail=order_data.get("error"))

    location_id = os.getenv("SQUARE_LOCATION_ID")
    order_res = create_order(
        location_id=location_id,
        line_items=order_data["line_items"],
        idempotency_key=f"admin-reactiv-order-{uuid.uuid4().hex}"
    )
    
    if not order_res.get("success"):
        raise HTTPException(status_code=400, detail=f"Order creation failed: {order_res.get('error')}")
        
    order_id = order_res.get("order_id")

    # 2. Create Subscription
    res = create_subscription(
        customer_id=customer.square_customer_id,
        location_id=location_id,
        plan_variation_id=customer.plan_variation_id,
        card_id=default_card.square_card_id,
        order_template_id=order_id,
        idempotency_key=f"admin-reactiv-sub-{uuid.uuid4().hex}"
    )
    
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=f"Square Subscription failed: {res.get('error')}")
        
    # 3. Update Local
    customer.square_subscription_id = res.get("subscription_id")
    customer.subscription_active = True
    customer.subscription_status = "ACTIVE"
    customer.order_template_id = order_id
    
    # Log
    log = SubscriptionLog(
        customer_id=customer.id,
        subscription_id=customer.square_subscription_id,
        action="ACTIVATE_ADMIN",
        effective_date=date.today()
    )
    db.add(log)
    db.commit()

    return {"success": True, "message": "Subscription activated instantly"}

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
