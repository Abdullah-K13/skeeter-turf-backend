import os
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from models.subscription import ItemVariation, SubscriptionPlan
from utils.square_client import get_catalog_prices, create_order

def prepare_subscription_order_items(db: Session, plan_variation_id: str, addons: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Unified logic to prepare line items and calculate totals for a subscription order template.
    Returns: {
        "line_items": list,
        "subtotal": float,
        "processing_fee": float,
        "total_amount": float
    }
    """
    # 1. Fetch Plan Details from DB
    plan_db = db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_variation_id == plan_variation_id).first()
    if not plan_db:
        return {"success": False, "error": f"Subscription plan for variation '{plan_variation_id}' not found in database."}

    # 2. Fetch the corresponding Order Item Variation ID for this plan
    plan_item = db.query(ItemVariation).filter(
        ItemVariation.item_type == "PLAN",
        ItemVariation.name == plan_db.plan_name
    ).first()
    
    if not plan_item:
        return {"success": False, "error": f"Order template item for plan '{plan_db.plan_name}' not found."}

    # 3. Prepare Line Items
    line_items = [
        {
            "quantity": "1",
            "catalog_object_id": plan_item.variation_id
        }
    ]
    
    all_variation_ids = [plan_item.variation_id]

    if addons:
        db_addons = db.query(ItemVariation).filter(
            ItemVariation.item_type == "ADDON",
            ItemVariation.variation_id.in_(addons)
        ).all()
        
        for addon in db_addons:
            line_items.append({
                "quantity": "1",
                "catalog_object_id": addon.variation_id
            })
            all_variation_ids.append(addon.variation_id)
            
    # 4. Fetch Prices for calculation
    prices = get_catalog_prices(all_variation_ids)
    
    # Calculate subtotal
    subtotal = plan_db.plan_cost
    if addons:
        for vid in addons:
            sq_price = prices.get(vid, 0)
            if sq_price > 0:
                subtotal += sq_price
            else:
                addon_db = next((a for a in db_addons if a.variation_id == vid), None)
                if addon_db:
                    subtotal += (addon_db.price or 0.0)
    
    # 5. Add Processing Fee
    processing_fee = round((subtotal * 0.040) + 0.10, 2)
    processing_fee_cents = int(processing_fee * 100)
    
    fee_item = db.query(ItemVariation).filter(ItemVariation.item_type == "FEE").first()
    if fee_item and fee_item.variation_id != "PROCESSING_FEE_PLACEHOLDER":
        line_items.append({
            "catalog_object_id": fee_item.variation_id,
            "quantity": "1",
            "base_price_money": {
                "amount": processing_fee_cents,
                "currency": "USD"
            }
        })
    else:
        line_items.append({
            "name": "Payment Processing Fee",
            "quantity": "1",
            "base_price_money": {
                "amount": processing_fee_cents,
                "currency": "USD"
            }
        })
        
    return {
        "success": True,
        "line_items": line_items,
        "subtotal": subtotal,
        "processing_fee": processing_fee,
        "total_amount": subtotal + processing_fee
    }
