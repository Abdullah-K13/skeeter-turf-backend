import os
from dotenv import load_dotenv

load_dotenv()

from utils.square_client import get_subscription_plans

res = get_subscription_plans()
if not res.get("success"):
    print("Failed...", res)
else:
    for p in res.get("plans", []):
        name = p.get("name")
        for v in p.get("variations", []):
            phases = v.get("phases", [])
            cadence = "UNKNOWN"
            if phases:
                cadence = phases[0].get("cadence")
            print(f"Plan: {name} | Variation: {v.get('name')} | Cadence: {cadence} | ID: {v.get('id')}")
