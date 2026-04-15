"""
Quick test script to verify the Brevo (Sendinblue) API key is valid.
Sends a test email to confirm everything works.
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

import requests
import os
from dotenv import load_dotenv

load_dotenv()

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")

def test_api_key_validity():
    """Check if the API key is valid by hitting the account endpoint."""
    print("=" * 50)
    print("Testing Brevo API Key Validity...")
    print("=" * 50)

    url = "https://api.brevo.com/v3/account"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY
    }

    response = requests.get(url, headers=headers, timeout=10)

    if response.status_code == 200:
        data = response.json()
        print(f"✅ API Key is VALID!")
        print(f"   Company: {data.get('companyName', 'N/A')}")
        print(f"   Email:   {data.get('email', 'N/A')}")
        plan_info = data.get('plan', [])
        for p in plan_info:
            print(f"   Plan:    {p.get('type', 'N/A')} - Credits: {p.get('credits', 'N/A')}")
    else:
        print(f"❌ API Key is INVALID or expired!")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")

    return response.status_code == 200


def send_test_email(to_email: str):
    """Send a test email via Brevo to confirm delivery works."""
    print("\n" + "=" * 50)
    print(f"Sending test email to: {to_email}")
    print("=" * 50)

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": BREVO_API_KEY
    }

    payload = {
        "sender": {
            "name": "Skeeter Turf",
            "email": "noreply@skeeterturf.com"  # Must be a verified sender in Brevo
        },
        "to": [
            {"email": to_email}
        ],
        "subject": "Brevo API Test - Skeeter Turf",
        "htmlContent": """
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #10b981;">✅ Brevo API Test Successful!</h2>
            <p>If you're reading this, the Brevo email integration is working correctly.</p>
            <p style="color: #666; font-size: 12px;">Sent from Skeeter Turf Backend test script.</p>
        </body>
        </html>
        """
    }

    response = requests.post(url, json=payload, headers=headers, timeout=10)

    if response.status_code in [200, 201]:
        data = response.json()
        print(f"✅ Email sent successfully!")
        print(f"   Message ID: {data.get('messageId', 'N/A')}")
    else:
        print(f"❌ Failed to send email!")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")

    return response.status_code in [200, 201]


if __name__ == "__main__":
    if not BREVO_API_KEY:
        print("❌ BREVO_API_KEY not found in .env file!")
        exit(1)

    print(f"Using API Key: {BREVO_API_KEY[:12]}...{BREVO_API_KEY[-4:]}\n")

    # Step 1: Validate key
    is_valid = test_api_key_validity()

    if is_valid:
        # Step 2: Send test email (change this to your email)
        test_email = input("\nEnter email to send test to (or press Enter to skip): ").strip()
        if test_email:
            send_test_email(test_email)
        else:
            print("\nSkipped sending test email.")
    
    print("\n" + "=" * 50)
    print("Done!")
