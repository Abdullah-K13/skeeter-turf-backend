"""Self-check: out-of-season plans get a future start_date, which makes Square create the
subscription as PENDING (not ACTIVE) - and swap-plan rejects non-ACTIVE subscriptions.

Run: python scripts/test_schedule_start_date.py
"""
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")  # models import db.init, which demands one

from models.subscription_schedule import SubscriptionPlanSchedule
from utils.subscription_scheduler import get_next_active_month


def sched(start, end):
    return SubscriptionPlanSchedule(start_month=start, end_month=end, plan_name="x")


# Seeded schedules (db/init.py seed_db)
ground_control = sched(1, 2)    # Jan-Feb, the $150 plan
turf = sched(1, 11)             # Jan-Nov, the $100 plan
mosquito = sched(3, 11)

# November (today: 2026-11-05)
assert ground_control.is_month_active(11) is False, "Ground Control should be out of season in Nov"
assert turf.is_month_active(11) is True
assert mosquito.is_month_active(11) is True

# So a Ground Control signup in Nov is deferred to the next active month -> January, next year
nxt = get_next_active_month(ground_control, 11)
assert nxt == 1, nxt
start = datetime(2026 + 1, nxt, 1).strftime("%Y-%m-%d")
assert start == "2027-01-01", start

# Wrap-around ranges still work
assert sched(11, 2).is_month_active(12) is True
assert sched(11, 2).is_month_active(6) is False

print("OK - a Ground Control signup in November starts 2027-01-01, so Square holds it PENDING.")
print("     Local DB still writes subscription_status='ACTIVE' (routers/payment.py:698),")
print("     so the admin UI shows ACTIVE while Square refuses swap-plan on a non-ACTIVE subscription.")
