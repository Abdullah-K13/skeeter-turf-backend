import os
import requests
from dotenv import load_dotenv

load_dotenv()

from utils.square_client import search_subscriptions

def test_subscriptions():
    print("--- Testing search_subscriptions (all) ---")
    res_all = search_subscriptions()
    if res_all.get("success"):
        subs = res_all.get("subscriptions", [])
        print(f"Total subscriptions: {len(subs)}")
        if subs:
            # Print first one to see structure
            sub = subs[0]
            print("Sample Subscription Data:")
            print(sub)
    else:
        print(f"Failed: {res_all.get('error')}")

if __name__ == "__main__":
    test_subscriptions()
