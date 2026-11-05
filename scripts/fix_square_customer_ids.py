"""Repoint customers at their current Square customer id.

    python scripts/fix_square_customer_ids.py            # dry run, writes nothing
    python scripts/fix_square_customer_ids.py --apply

Square merges duplicate customer records (creation_source MERGE). The old id keeps
resolving on GET /v2/customers/{id}, and a subscription search still returns the
subscription under it - but an INVOICE search returns nothing for a merged-away id.
That is why sync-invoices reported success with 0 synced for customers whose Square
records had been merged: the backend was asking about an id Square no longer files
invoices under.

For each customer this compares the stored id against the record Square returns for
their email, and only proposes a change when the stored id has no invoices and the
email-resolved one does.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from db.init import SessionLocal
from models.user import Customer
from utils.square_client import get_square_customer_by_email, search_invoices


def invoice_count(square_customer_id):
    res = search_invoices(square_customer_id)
    return len(res.get("invoices") or []) if res.get("success") else -1


def decide(stored_id, email, count_fn, lookup_fn):
    """Return (new_id_or_None, note). Only repoints when the stored id has no invoices
    and the email-resolved record does - never on a hunch, since this moves billing
    history between records."""
    stored_n = count_fn(stored_id)
    if stored_n > 0:
        return None, f"ok ({stored_n} invoices)"

    found = lookup_fn(email) if email else {"success": False}
    current = found.get("customer_id") if found.get("success") else None
    if not current or current == stored_id:
        return None, f"stored id has {stored_n} invoices, no better record found"

    current_n = count_fn(current)
    if current_n <= 0:
        return None, f"{current} has no invoices either; left alone"
    return current, f"{stored_id} ({stored_n}) -> {current} ({current_n} invoices)"


def main():
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        rows = db.query(Customer).filter(Customer.square_customer_id.isnot(None)).order_by(Customer.id).all()
        print(f"{len(rows)} customers with a Square id{'' if apply else '  (dry run, nothing written)'}\n")

        fixed = ok = skipped = 0
        for c in rows:
            new_id, note = decide(c.square_customer_id, c.email, invoice_count, get_square_customer_by_email)
            if new_id:
                print(f"  customer {c.id:>4}  {(c.email or ''):38} {note}")
                if apply:
                    c.square_customer_id = new_id
                fixed += 1
            elif note.startswith("ok"):
                ok += 1
            else:
                skipped += 1
                print(f"  customer {c.id:>4}  {(c.email or ''):38} {note}")

        if apply:
            db.commit()
        print(f"\n{ok} already correct, {fixed} {'repointed' if apply else 'would be repointed'}, {skipped} need a look.")
        if not apply and fixed:
            print("Re-run with --apply to write, then: python scripts/backfill_invoices.py")
    finally:
        db.close()


if __name__ == "__main__":
    main()
