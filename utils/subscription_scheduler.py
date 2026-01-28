"""
Subscription Scheduler Utility

Handles automatic pause/resume of subscriptions based on plan schedules.
This should be run at the start of each month (e.g., via cron job or scheduled task).
"""
import logging
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from db.init import SessionLocal
from models.user import Customer
from models.subscription import SubscriptionPlan
from models.subscription_schedule import SubscriptionPlanSchedule
from utils.square_client import pause_subscription, resume_subscription

logger = logging.getLogger(__name__)

# Month name mapping for logging
MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}


def get_all_plan_schedules(db: Session) -> List[SubscriptionPlanSchedule]:
    """Fetch all subscription plan schedules from the database."""
    return db.query(SubscriptionPlanSchedule).all()


def get_schedule_for_plan(db: Session, plan_name: str) -> SubscriptionPlanSchedule:
    """Get the schedule for a specific plan by name (case-insensitive partial match)."""
    return db.query(SubscriptionPlanSchedule).filter(
        SubscriptionPlanSchedule.plan_name.ilike(f"%{plan_name}%")
    ).first()


def is_plan_active_for_month(schedule: SubscriptionPlanSchedule, month: int) -> bool:
    """Check if a plan is active for the given month (1-12)."""
    if not schedule:
        return True  # If no schedule found, assume always active
    return schedule.is_month_active(month)


def get_customers_with_plan(db: Session, plan_name: str) -> List[Customer]:
    """Get all customers subscribed to a plan (by name pattern match)."""
    # Match plan name in the plan_id or subscription status
    return db.query(Customer).filter(
        Customer.subscription_active == True,
        Customer.plan_id.isnot(None)
    ).all()


def process_monthly_subscription_schedules(dry_run: bool = False) -> Dict[str, Any]:
    """
    Main function to process subscription schedules for the current month.
    
    Args:
        dry_run: If True, only log what would happen without making changes
        
    Returns:
        Dict with counts of paused and resumed subscriptions
    """
    db = SessionLocal()
    results = {
        "current_month": datetime.now().month,
        "month_name": MONTH_NAMES[datetime.now().month],
        "paused": [],
        "resumed": [],
        "errors": [],
        "dry_run": dry_run
    }
    
    try:
        current_month = datetime.now().month
        schedules = get_all_plan_schedules(db)
        
        logger.info(f"Processing subscription schedules for {MONTH_NAMES[current_month]}...")
        logger.info(f"Found {len(schedules)} plan schedules to process")
        
        for schedule in schedules:
            plan_active = is_plan_active_for_month(schedule, current_month)
            logger.info(f"Plan '{schedule.plan_name}': Active={plan_active} (months {schedule.start_month}-{schedule.end_month})")
            
            # Get customers with this plan
            # Match by checking if plan_id contains the plan name
            customers = db.query(Customer).filter(
                Customer.square_subscription_id.isnot(None)
            ).all()
            
            for customer in customers:
                # Check if customer's plan matches this schedule
                customer_plan = None
                if customer.plan_id:
                    # Try to find matching plan
                    plan = db.query(SubscriptionPlan).filter(
                        SubscriptionPlan.id == int(customer.plan_id)
                    ).first() if customer.plan_id.isdigit() else None
                    
                    if plan:
                        customer_plan = plan.plan_name
                    else:
                        customer_plan = customer.plan_id
                
                if not customer_plan or schedule.plan_name.lower() not in customer_plan.lower():
                    continue
                
                logger.info(f"Processing customer {customer.id} ({customer.email}) with plan '{customer_plan}'")
                
                if not plan_active and customer.subscription_status == "ACTIVE":
                    # Plan is inactive this month - PAUSE the subscription
                    logger.info(f"  -> Pausing subscription {customer.square_subscription_id}")
                    
                    if not dry_run:
                        res = pause_subscription(customer.square_subscription_id)
                        if "errors" not in res:
                            customer.subscription_status = "PAUSED"
                            customer.subscription_paused_by_schedule = True
                            db.commit()
                            results["paused"].append({
                                "customer_id": customer.id,
                                "email": customer.email,
                                "plan": customer_plan
                            })
                        else:
                            results["errors"].append({
                                "customer_id": customer.id,
                                "action": "pause",
                                "error": str(res["errors"])
                            })
                    else:
                        results["paused"].append({
                            "customer_id": customer.id,
                            "email": customer.email,
                            "plan": customer_plan,
                            "dry_run": True
                        })
                        
                elif plan_active and customer.subscription_status == "PAUSED" and customer.subscription_paused_by_schedule:
                    # Plan is active this month and was paused by schedule - RESUME
                    logger.info(f"  -> Resuming subscription {customer.square_subscription_id}")
                    
                    if not dry_run:
                        res = resume_subscription(customer.square_subscription_id)
                        if "errors" not in res:
                            customer.subscription_status = "ACTIVE"
                            customer.subscription_paused_by_schedule = False
                            db.commit()
                            results["resumed"].append({
                                "customer_id": customer.id,
                                "email": customer.email,
                                "plan": customer_plan
                            })
                        else:
                            results["errors"].append({
                                "customer_id": customer.id,
                                "action": "resume",
                                "error": str(res["errors"])
                            })
                    else:
                        results["resumed"].append({
                            "customer_id": customer.id,
                            "email": customer.email,
                            "plan": customer_plan,
                            "dry_run": True
                        })
        
        logger.info(f"Scheduler complete: {len(results['paused'])} paused, {len(results['resumed'])} resumed")
        
    except Exception as e:
        logger.error(f"Error in subscription scheduler: {str(e)}")
        results["errors"].append({"error": str(e)})
    finally:
        db.close()
    
    return results


def get_next_active_month(schedule: SubscriptionPlanSchedule, from_month: int) -> int:
    """
    Get the next active month for a plan schedule starting from a given month.
    Returns the next active month (1-12).
    """
    for i in range(12):
        check_month = ((from_month - 1 + i) % 12) + 1
        if schedule.is_month_active(check_month):
            return check_month
    return from_month  # Fallback


def calculate_subscription_start_date(plan_name: str, signup_date: datetime = None) -> str:
    """
    Calculate the appropriate start date for a subscription based on the plan schedule.
    
    If the current month is inactive for the plan, returns the first day of the next active month.
    
    Args:
        plan_name: Name of the subscription plan
        signup_date: Date of signup (defaults to now)
        
    Returns:
        Start date string in YYYY-MM-DD format
    """
    db = SessionLocal()
    try:
        if signup_date is None:
            signup_date = datetime.now()
        
        current_month = signup_date.month
        current_year = signup_date.year
        
        schedule = get_schedule_for_plan(db, plan_name)
        
        if not schedule:
            # No schedule found, start immediately
            return None
        
        if schedule.is_month_active(current_month):
            # Current month is active, start immediately
            return None
        
        # Find the next active month
        next_month = get_next_active_month(schedule, current_month)
        
        # Calculate the year (might need to go to next year)
        if next_month < current_month:
            next_year = current_year + 1
        else:
            next_year = current_year
        
        start_date = datetime(next_year, next_month, 1)
        return start_date.strftime("%Y-%m-%d")
        
    finally:
        db.close()
