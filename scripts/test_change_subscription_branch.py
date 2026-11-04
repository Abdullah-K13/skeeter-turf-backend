"""Self-check for admin_change_subscription: it must branch on Square's live status,
not on the local subscription_status column.

Regression guarded: customer 15 read ACTIVE locally while Square had the subscription
CANCELED since 2026-03-16, so the endpoint called swap-plan and Square refused it with:
  BAD_REQUEST: The provided subscription `2991120f-...` must have a `ACTIVE` state to swap the plan.

Run: python scripts/test_change_subscription_branch.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SQUARE_LOCATION_ID", "L_TEST")

from fastapi import HTTPException
import utils.square_client as sq
import utils.subscription_logic as sl
from models.user import Customer
from models.subscription import SubscriptionPlan, PaymentMethod
import routers.admin as admin

NEW_VAR = "NEW_100_VARIATION"
OLD_VAR = "6JASEXSQRDN24HQLBGXM662N"
SUB_ID = "2991120f-34d8-4f3e-92d9-609d4102523e"

calls = []
EXISTING_SUBS = []


class FakeQuery:
    def __init__(self, db, model):
        self.db, self.model = db, model

    def get(self, _id):
        return self.db.customer

    def filter(self, *a, **k):
        return self

    def first(self):
        if self.model is SubscriptionPlan:
            return self.db.plan
        if self.model is PaymentMethod:
            return self.db.card
        return None

    def all(self):
        return []


class FakeDB:
    def __init__(self, customer, plan, card=None):
        self.customer, self.plan, self.added = customer, plan, []
        self.card = card

    def query(self, model):
        return FakeQuery(self, model)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass


def make_customer(status_in_db):
    c = Customer()
    c.id = 15
    c.email = "test@example.com"
    c.first_name, c.last_name = "Cary", "B"
    c.square_customer_id = "SQ_CUST"
    c.square_subscription_id = SUB_ID
    c.plan_variation_id = OLD_VAR
    c.subscription_active = status_in_db == "ACTIVE"
    c.subscription_status = status_in_db
    c.selected_addons = []
    return c


def stub_square(live_status):
    calls.clear()

    def retrieve_subscription(sid, include_actions=False):
        calls.append(("retrieve", sid))
        return {"success": True, "subscription": {
            "id": sid, "status": live_status, "plan_variation_id": OLD_VAR}}

    def swap_subscription_plan(subscription_id, new_plan_variation_id):
        calls.append(("swap", new_plan_variation_id))
        if live_status != "ACTIVE":
            # Square's verbatim 400, captured from production on 2026-11-05
            return {"success": False, "error": (
                "[{'code': 'BAD_REQUEST', 'detail': 'The provided subscription "
                "`%s` must have a `ACTIVE` state to swap the plan.', "
                "'category': 'INVALID_REQUEST_ERROR'}]" % subscription_id)}
        return {"success": True, "subscription": {}}

    def update_subscription(subscription_id=None, plan_variation_id=None,
                            order_template_id=None, card_id=None):
        calls.append(("update", order_template_id))
        return {"success": True, "subscription": {}}

    def create_subscription(**kw):
        calls.append(("create", kw.get("plan_variation_id")))
        return {"success": True, "subscription_id": "NEW_SUB_ID"}

    def create_order(**kw):
        return {"success": True, "order_id": "ORDER_1"}

    def get_subscriptions(customer_id=None, status=None, cursor=None):
        calls.append(("search", customer_id))
        return {"success": True, "subscriptions": EXISTING_SUBS[:]}

    sq.retrieve_subscription = retrieve_subscription
    sq.swap_subscription_plan = swap_subscription_plan
    sq.update_subscription = update_subscription
    sq.create_subscription = create_subscription
    sq.create_order = create_order
    sq.get_subscriptions = get_subscriptions
    sl.prepare_subscription_order_items = lambda db, var, addons: {"success": True, "line_items": []}


class Req:
    new_plan_variation_id = NEW_VAR
    addons = []


def run(db_status, live_status, db=None, card=None):
    stub_square(live_status)
    plan = SubscriptionPlan()
    plan.id = 1
    plan.plan_variation_id = NEW_VAR
    db = db or FakeDB(make_customer(db_status), plan, card)
    out = admin.admin_change_subscription(15, Req(), db=db, current_user={"role": "admin"})
    return out, db


# 1. The actual bug: DB says ACTIVE, Square says CANCELED -> must create, never swap.
db = FakeDB(make_customer("ACTIVE"), None)
db.plan = SubscriptionPlan(); db.plan.id = 1; db.plan.plan_variation_id = NEW_VAR
# a dead subscription needs a card to recreate; PaymentMethod lookup returns None in FakeQuery,
# so the endpoint must reject cleanly rather than swap.
try:
    run("ACTIVE", "CANCELED", db)
    raise AssertionError("expected a 400 about the missing card")
except HTTPException as e:
    assert e.status_code == 400 and "payment method" in e.detail.lower(), e.detail
assert ("swap", NEW_VAR) not in calls, f"swap-plan was called on a CANCELED subscription: {calls}"
assert db.customer.subscription_status == "CANCELED", db.customer.subscription_status
assert db.customer.subscription_active is False
print("1. CANCELED in Square -> no swap attempted, local status resynced to CANCELED  OK")

# 2. Genuinely active -> swaps, and uses Square's variation for the comparison.
out, db = run("ACTIVE", "ACTIVE")
assert out["action"] == "CHANGE_PLAN", out
assert ("swap", NEW_VAR) in calls, calls
assert db.customer.plan_variation_id == NEW_VAR
print("2. ACTIVE in Square -> swap-plan called, plan updated                          OK")

# 3. Already on the requested variation -> no pointless swap, order template still refreshed.
class SameReq(Req):
    new_plan_variation_id = OLD_VAR
stub_square("ACTIVE")
plan = SubscriptionPlan(); plan.id = 1; plan.plan_variation_id = OLD_VAR
db = FakeDB(make_customer("ACTIVE"), plan)
admin.admin_change_subscription(15, SameReq(), db=db, current_user={"role": "admin"})
assert not any(c[0] == "swap" for c in calls), calls
assert ("update", "ORDER_1") in calls, calls
print("3. Same variation -> swap skipped, order template still updated                OK")

# 4. Paused -> clear error instead of a Square rejection or a duplicate subscription.
try:
    run("ACTIVE", "PAUSED")
    raise AssertionError("expected a 400 for PAUSED")
except HTTPException as e:
    assert e.status_code == 400 and "paused" in e.detail.lower(), e.detail
assert not any(c[0] in ("swap", "create") for c in calls), calls
print("4. PAUSED in Square -> explicit 400, no swap and no duplicate subscription     OK")

# 5. Money guard: the stored sub id is dead, but Square still bills this customer under
#    another subscription -> refuse rather than stack a second charge on the same card.
#    This is the shape of the real Cary case: sub 2991120f CANCELED, dc85c038 still ACTIVE.
card = PaymentMethod()
card.square_card_id = "ccof:TEST"
card.is_default = True
EXISTING_SUBS[:] = [{"id": "dup", "status": "ACTIVE", "location_id": "L_TEST"}]
try:
    run("ACTIVE", "CANCELED", card=card)
    raise AssertionError("expected a 400 about the existing live subscription")
except HTTPException as e:
    assert e.status_code == 400 and "already has a live subscription" in e.detail, e.detail
assert not any(c[0] == "create" for c in calls), f"created a second subscription: {calls}"
EXISTING_SUBS[:] = []
print("5. Dead sub id but customer still billed HERE -> refuse, no 2nd charge      OK")

# 6. Same person live at ANOTHER brand's location (Adams) must NOT block a subscription
#    here. Cary is meant to be a customer of both Skeeterman and Adams at once.
EXISTING_SUBS[:] = [{"id": "dc85c038-a39c-42b1-96ba-4006a673466e",
                     "status": "ACTIVE", "location_id": "L630MQ9S2T49X"}]
out, db = run("ACTIVE", "CANCELED", card=card)
assert out["action"] == "ACTIVATE", out
assert any(c[0] == "create" for c in calls), calls
assert db.customer.square_subscription_id == "NEW_SUB_ID", db.customer.square_subscription_id
EXISTING_SUBS[:] = []
print("6. Live at another brand's location -> allowed, creates here as normal       OK")

print("\nall checks passed")
