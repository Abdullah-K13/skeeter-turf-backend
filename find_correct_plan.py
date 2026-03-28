import os
import json
from dotenv import load_dotenv
load_dotenv()

from utils.square_client import get_square_base_url, get_square_headers
import requests

url = f"{get_square_base_url()}/v2/catalog/search"
headers = get_square_headers()

payload = {
    "query": {
        "text_query": {
            "keywords": ["Mosquito"]
        }
    }
}

res = requests.post(url, json=payload, headers=headers)
data = res.json()

with open("mosquito_search_results.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"Found {len(data.get('objects', []))} objects matching 'Mosquito'. Saved to mosquito_search_results.json")
