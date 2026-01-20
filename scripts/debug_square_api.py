import os
import sys
import requests
import json

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

SQUARE_ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN")
SQUARE_ENVIRONMENT = os.getenv("SQUARE_ENVIRONMENT", "production")

SQUARE_API_BASE_URL = {
    "sandbox": "https://connect.squareupsandbox.com",
    "production": "https://connect.squareup.com"
}

BASE_URL = SQUARE_API_BASE_URL.get(SQUARE_ENVIRONMENT, SQUARE_API_BASE_URL["sandbox"])

def get_headers():
    return {
        "Square-Version": "2024-01-18",
        "Authorization": f"Bearer {SQUARE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

def test_query(payload_name, payload):
    print(f"\nTesting Payload: {payload_name}")
    print(json.dumps(payload, indent=2))
    
    url = f"{BASE_URL}/v2/subscriptions/search"
    res = requests.post(url, json=payload, headers=get_headers())
    
    if res.status_code == 200:
        data = res.json()
        subs = data.get("subscriptions", [])
        print(f"SUCCESS. Count: {len(subs)}")
        if subs:
            print(f"Sample Status: {subs[0].get('status')}")
    else:
        print(f"ERROR {res.status_code}: {res.text}")

def main():
    if not SQUARE_ACCESS_TOKEN:
        print("SQUARE_ACCESS_TOKEN not set")
        return

    # 1. Original failing payload (with statuses)
    test_query("Original (statuses)", {
        "query": {
            "filter": {
                "statuses": ["ACTIVE"]
            }
        }
    })

    # 2. Empty filter (Fetch all)
    test_query("Empty Filter", {
        "query": {
            "filter": {}
        }
    })
    
    # 3. No query field at all (might work?)
    # test_query("No Query", {}) # Usually search endpoints require query object

if __name__ == "__main__":
    main()
