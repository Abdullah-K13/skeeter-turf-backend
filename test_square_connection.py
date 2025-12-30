import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

SQUARE_ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN")
SQUARE_ENVIRONMENT = os.getenv("SQUARE_ENVIRONMENT", "sandbox")

def test_square_connection():
    print(f"Testing Square connection...")
    print(f"Environment: {SQUARE_ENVIRONMENT}")
    
    if not SQUARE_ACCESS_TOKEN:
        print("Error: SQUARE_ACCESS_TOKEN is not set in .env file.")
        return

    # Square API Base URLs
    base_url = "https://connect.squareupsandbox.com" if SQUARE_ENVIRONMENT.lower() == "sandbox" else "https://connect.squareup.com"
    url = f"{base_url}/v2/locations"
    
    headers = {
        "Square-Version": "2024-01-18",
        "Authorization": f"Bearer {SQUARE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        print(f"Sending request to: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            locations = data.get("locations", [])
            print("Connection Successful!")
            print(f"Found {len(locations)} location(s):")
            for loc in locations:
                print(f" - {loc.get('name')} (ID: {loc.get('id')})")
        else:
            print(f"Connection Failed! Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    test_square_connection()
