"""Backfill the invoices table from Square for every customer.

    python scripts/backfill_invoices.py --dry-run
    python scripts/backfill_invoices.py

Run it where DATABASE_URL resolves. Idempotent: existing rows are updated in place,
missing ones inserted, nothing deleted.

Needed because invoice rows were only ever created when an admin opened the
View Invoices dialog for a single customer, so most customers have no local
billing history even though Square holds every paid invoice.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from db.init import SessionLocal
from models.user import Customer
from utils.invoice_sync import sync_invoices_for_customer


def main():
    dry = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        rows = db.query(Customer).filter(Customer.square_customer_id.isnot(None)).order_by(Customer.id).all()
        print(f"{len(rows)} customers with a Square id{' (dry run, nothing written)' if dry else ''}\n")

        total_new = total_upd = failed = 0
        for c in rows:
            res = sync_invoices_for_customer(db, c, commit=not dry)
            if not res.get("success"):
                failed += 1
                print(f"  customer {c.id:>4}  {c.email:40} FAILED: {res.get('error')}")
                continue
            total_new += res["synced"]
            total_upd += res["updated"]
            if res["synced"] or res["updated"]:
                print(f"  customer {c.id:>4}  {c.email:40} +{res['synced']} new, {res['updated']} updated")

        if dry:
            db.rollback()
        print(f"\n{total_new} invoices inserted, {total_upd} updated, {failed} customers failed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
