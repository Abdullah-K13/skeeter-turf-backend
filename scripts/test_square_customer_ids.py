"""Self-check for the merged-customer repair decision.

Square merges duplicate customer records. The merged-away id still resolves on GET
and still returns the subscription, but an invoice search under it returns nothing,
which is why sync-invoices reported success with 0 synced for seven customers.

Repointing moves which Square record a customer's billing history is read from, so
the rule is deliberately narrow: only when the stored id has no invoices AND the
email-resolved record does.

Run: python scripts/test_square_customer_ids.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import importlib.util
spec = importlib.util.spec_from_file_location(
    "fixids", os.path.join(os.path.dirname(__file__), "fix_square_customer_ids.py"))
fixids = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixids)
decide = fixids.decide

# Real shape: Clare Kinlaw, stored id merged away, invoices on the surviving record.
STORED, CURRENT = "ZZD3ZSVXGNG7CHCJ222CWD0QKC", "1AWJHQBTQD8C9MHB1NHP6ESK2W"
counts = {STORED: 0, CURRENT: 11}
lookup = lambda e: {"success": True, "customer_id": CURRENT}

new_id, note = decide(STORED, "cfkinlaw@gmail.com", counts.get, lookup)
assert new_id == CURRENT, (new_id, note)
print("1. Merged-away id with invoices on the survivor -> repoint               OK")

# Healthy customer: never touched, and no lookup is even attempted.
def exploding_lookup(e):
    raise AssertionError("looked up an email for a customer that was already fine")
new_id, note = decide(CURRENT, "cfkinlaw@gmail.com", counts.get, exploding_lookup)
assert new_id is None and note.startswith("ok"), (new_id, note)
print("2. Stored id already has invoices -> left alone, no lookup              OK")

# Candidate has no invoices either: do not move billing history on a guess.
new_id, note = decide(STORED, "x@y.com", lambda cid: 0, lambda e: {"success": True, "customer_id": "OTHER"})
assert new_id is None and "no invoices either" in note, (new_id, note)
print("3. Candidate also empty -> no change                                    OK")

# Email resolves to the same id, or not at all.
new_id, _ = decide(STORED, "x@y.com", lambda cid: 0, lambda e: {"success": True, "customer_id": STORED})
assert new_id is None
new_id, _ = decide(STORED, "x@y.com", lambda cid: 0, lambda e: {"success": False})
assert new_id is None
new_id, _ = decide(STORED, None, lambda cid: 0, exploding_lookup)
assert new_id is None
print("4. Same id, no match, or no email -> no change                          OK")

# A Square error (-1) must not be read as "empty", which would trigger a repoint.
new_id, note = decide(STORED, "x@y.com", lambda cid: -1, lambda e: {"success": True, "customer_id": "OTHER"})
assert new_id is None, (new_id, note)
print("5. Square error counts as unknown, not empty -> no change               OK")

print("\nall checks passed")
