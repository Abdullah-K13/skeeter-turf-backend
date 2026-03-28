import os
import json
from dotenv import load_dotenv
load_dotenv()

from utils.square_client import retrieve_subscription, get_square_base_url, get_square_headers
import requests

sub_ids = [
    "ab793446-e780-47f6-af95-ebb7fc5bd3a9", # Crystal Baker
    "41c0aa4a-ff1e-4808-b053-a6211047b518", # Brian Keigher
    "59385a8d-ae42-445b-b67c-1fd7877a38f5"  # Christa Fulenwider
]

var_ids = set()
for sub_id in sub_ids:
    res = retrieve_subscription(sub_id)
    sub = res.get("subscription", {})
    var_id = sub.get("plan_variation_id")
    if var_id:
        var_ids.add(var_id)

url = f"{get_square_base_url()}/v2/catalog/batch-retrieve"
headers = get_square_headers()
payload = {"object_ids": list(var_ids)}
res = requests.post(url, json=payload, headers=headers)
data = res.json()

results = []
for obj in data.get("objects", []):
    if obj["type"] == "SUBSCRIPTION_PLAN_VARIATION":
        var_data = obj.get("subscription_plan_variation_data", {})
        name = var_data.get("name")
        plan_id = var_data.get("subscription_plan_id")
        phases = var_data.get("phases", [])
        cadence = phases[0].get("cadence") if phases else "UNKNOWN"
        
        p_payload = {"object_ids": [plan_id]}
        p_res = requests.post(url, json=p_payload, headers=headers)
        p_data = p_res.json()
        p_name = "Unknown"
        if p_data.get("objects"):
            p_obj = p_data["objects"][0]
            p_name = p_obj.get("subscription_plan_data", {}).get("name")
            
        results.append({
            "variation_id": obj["id"],
            "variation_name": name,
            "plan_id": plan_id,
            "plan_name": p_name,
            "cadence": cadence
        })

with open("weekly_details.json", "w") as f:
    json.dump(results, f, indent=2)
