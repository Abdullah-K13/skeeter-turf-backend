"""Diagnose why a plan change fails. Usage: python scripts/diagnose_subscription.py <square_subscription_id> [new_plan_variation_id]

Read-only. Prints Square's real state next to what change-subscription needs.
"""
import sys, os, json
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from utils.square_client import retrieve_subscription

SWAPPABLE = {"ACTIVE"}

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sub_id = sys.argv[1]
    new_var = sys.argv[2] if len(sys.argv) > 2 else None

    res = retrieve_subscription(sub_id, include_actions=True)
    if not res.get("success"):
        sys.exit(f"Square lookup failed: {res.get('error')}")

    s = res["subscription"]
    print(json.dumps(s, indent=2))
    print("\n--- verdict ---")
    status = s.get("status")
    print(f"status            : {status}")
    print(f"start_date        : {s.get('start_date')}")
    print(f"canceled_date     : {s.get('canceled_date')}")
    print(f"plan_variation_id : {s.get('plan_variation_id')}")
    print(f"card_id           : {s.get('card_id')}")

    actions = s.get("actions") or []
    for a in actions:
        print(f"queued action     : {a.get('type')} id={a.get('id')} effective={a.get('effective_date')} -> {a.get('new_plan_variation_id')}")

    if new_var and new_var == s.get("plan_variation_id"):
        print("REASON: new plan variation == current one; backend skips swap entirely.")
    if any(a.get("type") == "SWAP_PLAN" for a in actions):
        print("REASON: a SWAP_PLAN action is already queued. Square rejects a second one until it clears.")
    if status not in SWAPPABLE:
        print(f"REASON: status is {status}, not ACTIVE. swap-plan only works on an ACTIVE subscription.")
        if status == "PENDING":
            print("        PENDING = start_date is in the future (set by calculate_subscription_start_date for out-of-season plans).")
    if status in SWAPPABLE and not actions:
        print("Square state looks swappable - the failure is elsewhere; paste the full backend error.")

if __name__ == "__main__":
    main()
