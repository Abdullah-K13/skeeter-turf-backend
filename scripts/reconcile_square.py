"""Read-only reconciliation: compare every customer row against Square.

Nothing is written. Run it on a host where DATABASE_URL resolves (e.g. inside the
compose network) and it prints every row whose local state disagrees with Square.

    python scripts/reconcile_square.py            # drift only
    python scripts/reconcile_square.py --all      # every customer

Why this exists: this backend has no inbound sync, so anything done in the Square
dashboard - a cancellation, a re-created customer, a plan swap - never reached the
database. Customer 15 read ACTIVE for eight months after Square canceled them.
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from db.init import SessionLocal
from models.user import Customer
from utils.square_client import (
    get_square_base_url, get_square_headers,
    retrieve_subscription, get_square_customer_by_id, get_subscriptions,
    get_square_customer_by_email, search_invoices,
)
import requests

LOCATION_ID = os.getenv("SQUARE_LOCATION_ID")
DEAD = ("CANCELED", "DEACTIVATED")


def square_customers_by_email():
    """Every customer in the Square account, grouped by email, to spot split records."""
    out, cursor = defaultdict(list), None
    while True:
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        j = requests.get(f"{get_square_base_url()}/v2/customers",
                         params=params, headers=get_square_headers(), timeout=30).json()
        for c in j.get("customers", []):
            email = (c.get("email_address") or "").strip().lower()
            if email:
                out[email].append(c)
        cursor = j.get("cursor")
        if not cursor:
            return out


def check(cust, dupes):
    """Return a list of problem strings for one local row."""
    problems = []

    if not cust.square_customer_id:
        if cust.subscription_active:
            problems.append("active locally but has no Square customer id")
        return problems

    if not get_square_customer_by_id(cust.square_customer_id).get("success"):
        problems.append(f"Square customer {cust.square_customer_id} does not exist (deleted?)")

    email = (cust.email or "").strip().lower()
    if len(dupes.get(email, [])) > 1:
        ids = ", ".join(c["id"] for c in dupes[email])
        problems.append(f"email has {len(dupes[email])} Square customer records: {ids}")

    # Square merges duplicate customers. The merged-away id still resolves and still
    # returns the subscription, but invoice search under it returns nothing - so
    # invoices silently stop syncing. Detect it by asking for the email's record.
    inv = search_invoices(cust.square_customer_id)
    if inv.get("success") and not inv.get("invoices"):
        found = get_square_customer_by_email(cust.email) if cust.email else {"success": False}
        current = found.get("customer_id") if found.get("success") else None
        if current and current != cust.square_customer_id:
            other = search_invoices(current)
            n = len(other.get("invoices") or []) if other.get("success") else 0
            if n:
                problems.append(
                    f"stored Square id {cust.square_customer_id} has no invoices, but {current} "
                    f"(same email) has {n} - looks merged away; see scripts/fix_square_customer_ids.py")

    if not cust.square_subscription_id:
        if cust.subscription_active:
            problems.append(f"marked {cust.subscription_status} locally but has no subscription id")
        return problems

    live = retrieve_subscription(cust.square_subscription_id)
    if not live.get("success"):
        problems.append(f"subscription {cust.square_subscription_id} unreadable: {live.get('error')}")
        return problems

    sub = live["subscription"]
    status = sub.get("status")

    if status != cust.subscription_status:
        problems.append(f"status: local {cust.subscription_status!r} vs Square {status!r}")
    if cust.subscription_active != (status == "ACTIVE"):
        problems.append(f"subscription_active={cust.subscription_active} but Square says {status}")
    if sub.get("plan_variation_id") != cust.plan_variation_id:
        problems.append(f"plan: local {cust.plan_variation_id} vs Square {sub.get('plan_variation_id')}")
    if LOCATION_ID and sub.get("location_id") != LOCATION_ID:
        problems.append(f"subscription lives at location {sub.get('location_id')}, not ours ({LOCATION_ID})")

    if status in DEAD:
        others = [s for s in (get_subscriptions(customer_id=cust.square_customer_id).get("subscriptions") or [])
                  if s.get("status") not in DEAD and s.get("location_id") == LOCATION_ID]
        if others:
            problems.append(f"stored subscription is {status}, but {others[0]['id']} is live at our location")

    return problems


def main():
    show_all = "--all" in sys.argv
    db = SessionLocal()
    try:
        dupes = square_customers_by_email()
        rows = db.query(Customer).order_by(Customer.id).all()
        print(f"Checking {len(rows)} customers against Square (location {LOCATION_ID})\n")

        bad = 0
        for c in rows:
            problems = check(c, dupes)
            if problems:
                bad += 1
                print(f"customer {c.id}  {c.email}")
                for p in problems:
                    print(f"    - {p}")
            elif show_all:
                print(f"customer {c.id}  {c.email}  ok")

        print(f"\n{bad} of {len(rows)} customers disagree with Square.")
        print("Nothing was written. Fix the rows you recognise, then re-run.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
