"""Self-check for the Square webhook: signature enforcement + status sync.

Guards the two reasons the DB silently stopped matching Square:
  - the handlers listened for event names Square does not emit
  - nothing verified who was calling, so enabling webhooks would have been unsafe

Run: python scripts/test_webhook_sync.py
"""
import os, sys, json, base64, hashlib, hmac, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["SQUARE_WEBHOOK_SIGNATURE_KEY"] = "test-signature-key"
os.environ["SQUARE_WEBHOOK_URL"] = "https://api1.protownnetwork.com/webhooks/square"

from fastapi import HTTPException
from models.user import Customer
import routers.webhooks as wh

# Event names Square actually emits, from GET /v2/webhooks/event-types on this account
REAL_EVENTS = {"invoice.canceled", "invoice.created", "invoice.deleted", "invoice.payment_made",
               "invoice.published", "invoice.refunded", "invoice.scheduled_charge_failed",
               "invoice.updated", "subscription.created", "subscription.updated"}

SUB_ID = "dc85c038-a39c-42b1-96ba-4006a673466e"


class FakeQuery:
    def __init__(self, db): self.db = db
    def filter(self, *a, **k): return self
    def first(self): return self.db.customer


class FakeDB:
    def __init__(self, customer): self.customer, self.added = customer, []
    def query(self, model): return FakeQuery(self)
    def add(self, obj): self.added.append(obj)
    def commit(self): pass


class FakeRequest:
    def __init__(self, body: bytes, sig): self._body, self.headers = body, {"x-square-hmacsha256-signature": sig}
    async def body(self): return self._body


def sign(body: bytes) -> str:
    return base64.b64encode(hmac.new(b"test-signature-key",
                                     os.environ["SQUARE_WEBHOOK_URL"].encode() + body,
                                     hashlib.sha256).digest()).decode()


def customer():
    c = Customer()
    c.id, c.email = 15, "caryb4360@gmail.com"
    c.square_subscription_id = SUB_ID
    c.subscription_status, c.subscription_active = "ACTIVE", True
    c.failed_payment_attempts = 0
    return c


def post(event, sig=None):
    body = json.dumps(event).encode()
    db = FakeDB(customer())
    req = FakeRequest(body, sig if sig is not None else sign(body))
    return asyncio.run(wh.square_webhook(req, db=db)), db


CANCEL_EVENT = {"type": "subscription.updated",
                "data": {"object": {"subscription": {"id": SUB_ID, "status": "CANCELED"}}}}

# 1. The event names the code listens for must be ones Square actually emits.
src = open(os.path.join(os.path.dirname(__file__), "..", "routers", "webhooks.py"), encoding="utf-8").read()
for dead in ("invoice.payment_failed", "invoice.payment_succeeded"):
    assert f'== "{dead}"' not in src, f"still listening for non-existent event {dead}"
import re
for ev in re.findall(r'event_type == "([^"]+)"', src):
    assert ev in REAL_EVENTS, f"{ev} is not a Square event type"
print("1. Every event the handler matches is one Square really emits            OK")

# 2. Forged / unsigned calls are refused.
for bad_sig in ("", "not-a-real-signature"):
    try:
        post(CANCEL_EVENT, sig=bad_sig)
        raise AssertionError("accepted a webhook with a bad signature")
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
print("2. Unsigned and forged webhooks rejected with 403                        OK")

# 3. A correctly signed cancellation syncs the DB - the thing that never happened for Cary.
_, db = post(CANCEL_EVENT)
assert db.customer.subscription_status == "CANCELED", db.customer.subscription_status
assert db.customer.subscription_active is False
assert any(getattr(l, "action", None) == "SQUARE_CANCELED" for l in db.added), db.added
print("3. Signed subscription.updated syncs status and logs it                  OK")

# 4. Fails closed when the signing key is not configured.
del os.environ["SQUARE_WEBHOOK_SIGNATURE_KEY"]
try:
    post(CANCEL_EVENT, sig="anything")
    raise AssertionError("accepted a webhook with no signing key configured")
except HTTPException as e:
    assert e.status_code == 403, e.status_code
os.environ["SQUARE_WEBHOOK_SIGNATURE_KEY"] = "test-signature-key"
print("4. No signing key configured -> fails closed, not open                   OK")

# 5. Invoice events must read the customer id from primary_recipient. Square invoices
#    have no top-level customer_id, so invoice.get("customer_id") always found nobody.
CUST = "C19T02WWWXM5B0KP8FHYABY7RR"
fail_event = {"type": "invoice.scheduled_charge_failed",
              "data": {"object": {"invoice": {"primary_recipient": {"customer_id": CUST}}}}}
c = customer(); c.square_customer_id = CUST; c.failed_payment_attempts = 2
body = json.dumps(fail_event).encode()
db = FakeDB(c)
asyncio.run(wh.square_webhook(FakeRequest(body, sign(body)), db=db))
assert c.failed_payment_attempts == 3, c.failed_payment_attempts
assert c.subscription_status == "SUSPENDED", c.subscription_status
print("5. Invoice events resolve the customer via primary_recipient              OK")

print("\nall checks passed")
