"""Self-check for invoice syncing.

Regression guarded: the invoices table was only ever written by an admin opening the
View Invoices dialog for one customer. Seven customers were reported as "invoices not
syncing" while Square held a complete, fully paid run for every one of them.

Run: python scripts/test_invoice_sync.py
"""
import os, sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

from models.subscription import Invoice
from models.user import Customer
import utils.invoice_sync as isync

# Shaped like real Square invoices for Clare Kinlaw ($156.10, PAID)
SQ = [
    {"id": "inv:0-A", "status": "PAID", "subscription_id": "sub-1",
     "payment_requests": [{"computed_amount_money": {"amount": 15610, "currency": "USD"}}],
     "created_at": "2026-10-29T12:00:00Z", "public_url": "https://sq/a"},
    {"id": "inv:0-B", "status": "PAID", "subscription_id": "sub-1",
     "payment_requests": [{"computed_amount_money": {"amount": 15610, "currency": "USD"}}],
     "scheduled_at": "2026-09-29", "public_url": "https://sq/b"},
    # no payment_requests - amount must fall back to next_payment_amount_money
    {"id": "inv:0-C", "status": "UNPAID", "subscription_id": "sub-1",
     "next_payment_amount_money": {"amount": 12490, "currency": "USD"},
     "created_at": "nonsense-date", "public_url": "https://sq/c"},
]


class FakeQuery:
    def __init__(self, db): self.db = db
    def filter(self, *a, **k): return self
    def first(self): return self.db._next_existing


class FakeDB:
    def __init__(self): self.added, self._next_existing, self.commits = [], None, 0
    def query(self, m): return FakeQuery(self)
    def add(self, o): self.added.append(o)
    def commit(self): self.commits += 1


def customer():
    c = Customer(); c.id, c.email = 42, "cfkinlaw@gmail.com"
    c.square_customer_id = "1AWJHQBTQD8C9MHB1NHP6ESK2W"
    return c


isync.search_invoices = lambda cid: {"success": True, "invoices": SQ}

# 1. A customer nobody ever clicked gets their whole history inserted.
db = FakeDB()
res = isync.sync_invoices_for_customer(db, customer())
assert res["success"] and res["synced"] == 3 and res["updated"] == 0, res
assert len(db.added) == 3, db.added
by_id = {i.square_invoice_id: i for i in db.added}
assert by_id["inv:0-A"].amount == 156.10, by_id["inv:0-A"].amount
assert by_id["inv:0-A"].due_date == date(2026, 10, 29), by_id["inv:0-A"].due_date
assert by_id["inv:0-B"].due_date == date(2026, 9, 29), by_id["inv:0-B"].due_date
print("1. Full history inserted, amounts and dates parsed                      OK")

# 2. Amount falls back when payment_requests is absent; bad dates don't explode.
assert by_id["inv:0-C"].amount == 124.90, by_id["inv:0-C"].amount
assert by_id["inv:0-C"].due_date == date.today(), by_id["inv:0-C"].due_date
print("2. Missing payment_requests and unparseable date handled                OK")

# 3. Re-running updates in place instead of duplicating.
db2 = FakeDB()
db2._next_existing = Invoice(square_invoice_id="inv:0-A", customer_id=42, amount=1.0, status="UNPAID")
res2 = isync.sync_invoices_for_customer(db2, customer())
assert res2["synced"] == 0 and res2["updated"] == 3, res2
assert db2.added == [], db2.added
assert db2._next_existing.status in ("PAID", "UNPAID")
print("3. Re-sync updates existing rows, inserts no duplicates                 OK")

# 4. A customer with no Square id fails cleanly rather than raising.
c = customer(); c.square_customer_id = None
res3 = isync.sync_invoices_for_customer(FakeDB(), c)
assert res3["success"] is False and res3["synced"] == 0, res3
print("4. Customer without a Square id fails cleanly                           OK")

# 5. A Square error is reported, not swallowed into a false success.
isync.search_invoices = lambda cid: {"success": False, "error": "boom"}
res4 = isync.sync_invoices_for_customer(FakeDB(), customer())
assert res4["success"] is False and res4["error"] == "boom", res4
print("5. Square failure surfaces as an error, not a silent empty sync         OK")

print("\nall checks passed")
