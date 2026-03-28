import requests
import json

# We need an admin JWT to query /customers on the live API. 
# But wait, we can also try the public endpoints or create a script that just uses the local square client to search for the user.
# Actually, the user says we can query the backend from this url https://api1.protownnetwork.com.
# If they didn't provide credentials, maybe some endpoints are open or we need to query through square directly.
# Let's see if /subscription-plans is open on the live API.
try:
    res = requests.get("https://api1.protownnetwork.com/subscription-plans", timeout=10)
    print("Live plans:", json.dumps(res.json(), indent=2))
except Exception as e:
    print("Error:", e)

# The user wants to know WHICH customer got a weekly plan.
# Did they provide the name? "one of my customer got susbcribed to a weekly cadence". No name provided.
# Let's search square subscriptions directly for any subscriptions that have a weekly cadence.
