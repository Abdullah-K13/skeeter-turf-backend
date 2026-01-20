import requests
import json

def test_addons():
    try:
        url = "http://127.0.0.1:8000/payments/addons/db"
        response = requests.get(url)
        data = response.json()
        print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_addons()
