"""Register (or inspect) this backend's Square webhook subscription.

    python scripts/register_webhook.py --list
    python scripts/register_webhook.py https://api.example.com/webhooks/square

Square prints the signature key ONCE, on creation. Put it in .env as
SQUARE_WEBHOOK_SIGNATURE_KEY, together with the exact URL you registered as
SQUARE_WEBHOOK_URL - Square signs over that URL, so it must match character for
character or every delivery is rejected.

Deploy the code BEFORE registering. Square starts posting immediately, and an
endpoint without the signing key configured rejects everything by design.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import requests
from utils.square_client import get_square_base_url, get_square_headers

# Only events this backend actually handles - see routers/webhooks.py
EVENTS = [
    "subscription.created",
    "subscription.updated",
    "invoice.payment_made",
    "invoice.scheduled_charge_failed",
]


def listing():
    r = requests.get(f"{get_square_base_url()}/v2/webhooks/subscriptions",
                     params={"include_disabled": "true"}, headers=get_square_headers(), timeout=20)
    subs = r.json().get("subscriptions", [])
    if not subs:
        print("No webhook subscriptions registered. Square has never called this backend.")
        return
    for s in subs:
        print(f"{s.get('id')}  enabled={s.get('enabled')}  {s.get('name')}")
        print(f"   url   : {s.get('notification_url')}")
        print(f"   events: {s.get('event_types')}")


def create(url):
    payload = {"subscription": {
        "name": os.getenv("SQUARE_WEBHOOK_NAME", "backend-subscription-sync"),
        "event_types": EVENTS,
        "notification_url": url,
        "api_version": "2024-01-18",
    }}
    r = requests.post(f"{get_square_base_url()}/v2/webhooks/subscriptions",
                      json=payload, headers=get_square_headers(), timeout=20)
    data = r.json()
    if "subscription" not in data:
        sys.exit(f"Failed: {data.get('errors')}")

    sub = data["subscription"]
    print(f"Created webhook subscription {sub.get('id')}")
    print(f"  url   : {sub.get('notification_url')}")
    print(f"  events: {sub.get('event_types')}")
    print("\nAdd these to .env and redeploy:\n")
    print(f'SQUARE_WEBHOOK_URL={sub.get("notification_url")}')
    print(f'SQUARE_WEBHOOK_SIGNATURE_KEY={sub.get("signature_key")}')
    print("\nThe signature key is shown only now. Square will not repeat it.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a]
    if not args or args[0] == "--list":
        listing()
    elif args[0].startswith("https://"):
        create(args[0])
    else:
        sys.exit(__doc__)
