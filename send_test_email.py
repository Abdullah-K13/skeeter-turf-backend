import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests, os
from dotenv import load_dotenv
load_dotenv()

key = os.getenv("BREVO_API_KEY")
r = requests.post("https://api.brevo.com/v3/smtp/email", json={
    "sender": {"name": "Skeeter Turf", "email": "info@skeetermanandturfninja.net"},
    "to": [{"email": "abdullahk4803@gmail.com"}],
    "subject": "Brevo API Test - Skeeter Turf",
    "htmlContent": "<h2 style='color:#10b981'>Brevo API Test Successful!</h2><p>If you are reading this, the Brevo email integration is working correctly.</p>"
}, headers={"accept": "application/json", "content-type": "application/json", "api-key": key}, timeout=10)

print(f"Status: {r.status_code}")
print(f"Response: {r.text}")
if r.status_code in [200, 201]:
    print("✅ Email sent successfully!")
else:
    print("❌ Failed to send email")
