import json
from dotenv import load_dotenv
load_dotenv()
import requests
from utils.square_client import get_square_base_url, get_square_headers

url = f"{get_square_base_url()}/v2/catalog/search"
headers = get_square_headers()

payload = {
    "object_types": ["SUBSCRIPTION_PLAN_VARIATION", "SUBSCRIPTION_PLAN"]
}

res = requests.post(url, json=payload, headers=headers)
data = res.json()

plans = {}
variations = []

for obj in data.get("objects", []):
    if obj["type"] == "SUBSCRIPTION_PLAN":
        plans[obj["id"]] = obj.get("subscription_plan_data", {}).get("name", "Unknown Plan")

for obj in data.get("objects", []):
    if obj["type"] == "SUBSCRIPTION_PLAN_VARIATION":
        var_data = obj.get("subscription_plan_variation_data", {})
        plan_id = var_data.get("subscription_plan_id")
        name = var_data.get("name")
        phases = var_data.get("phases", [])
        cadence = phases[0].get("cadence") if phases else "UNKNOWN"
        variations.append({
            "var_id": obj["id"],
            "var_name": name,
            "plan_id": plan_id,
            "plan_name": plans.get(plan_id, 'Unknown Plan'),
            "cadence": cadence
        })

with open("all_variations.json", "w", encoding="utf-8") as f:
    json.dump(variations, f, indent=2)

print("Saved variations.")
