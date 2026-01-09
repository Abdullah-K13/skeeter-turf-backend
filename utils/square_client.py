"""
Square API Client Wrapper
Handles all Square API interactions for payment processing and subscription management.
"""
import os
import logging
import requests
import uuid
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Square Configuration
SQUARE_ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN", "")
SQUARE_ENVIRONMENT = os.getenv("SQUARE_ENVIRONMENT", "production")
SQUARE_LOCATION_ID = os.getenv("SQUARE_LOCATION_ID", "")

# Square API Base URLs
SQUARE_API_BASE_URL = {
    "sandbox": "https://connect.squareupsandbox.com",
    "production": "https://connect.squareup.com"
}

def get_square_base_url() -> str:
    """Get the base URL for Square API based on environment"""
    return SQUARE_API_BASE_URL.get(SQUARE_ENVIRONMENT, SQUARE_API_BASE_URL["sandbox"])

def get_square_headers() -> Dict[str, str]:
    """Get headers for Square API requests"""
    if not SQUARE_ACCESS_TOKEN:
        raise ValueError("SQUARE_ACCESS_TOKEN is not set in environment variables")
    
    return {
        "Square-Version": "2024-01-18",
        "Authorization": f"Bearer {SQUARE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

# --- Payment Operations ---

def process_payment(
    source_id: str,
    amount: float,
    idempotency_key: str,
    location_id: Optional[str] = None
) -> Dict[str, Any]:
    """Process a payment using Square Payments API."""
    location = location_id or SQUARE_LOCATION_ID
    amount_cents = int(amount * 100)
    
    url = f"{get_square_base_url()}/v2/payments"
    headers = get_square_headers()
    
    payload = {
        "source_id": source_id,
        "idempotency_key": idempotency_key,
        "amount_money": {
            "amount": amount_cents,
            "currency": "USD"
        },
        "location_id": location
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Error processing payment: {str(e)}")
        return {"errors": [{"detail": str(e)}]}

def get_payment_status(transaction_id: str) -> Dict[str, Any]:
    """Get payment status from Square."""
    try:
        url = f"{get_square_base_url()}/v2/payments/{transaction_id}"
        headers = get_square_headers()
        response = requests.get(url, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Error getting payment status: {str(e)}")
        return {"errors": [{"detail": str(e)}]}

# --- Customer Operations ---

def create_square_customer(
    given_name: str,
    family_name: str,
    email: str,
    phone_number: Optional[str] = None,
    address: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a customer in Square."""
    try:
        url = f"{get_square_base_url()}/v2/customers"
        headers = get_square_headers()
        
        payload = {
            "given_name": given_name,
            "family_name": family_name,
            "email_address": email
        }
        if phone_number: payload["phone_number"] = phone_number
        if address: payload["address"] = address
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()
        
        if "customer" in data:
            return {"success": True, "customer": data["customer"], "customer_id": data["customer"]["id"]}
        return {"success": False, "error": str(data.get("errors", "Unknown error"))}
    except Exception as e:
        logger.error(f"Error creating customer: {str(e)}")
        return {"success": False, "error": str(e)}

def get_square_customer_by_id(customer_id: str) -> Dict[str, Any]:
    """Get a Square customer by ID."""
    try:
        url = f"{get_square_base_url()}/v2/customers/{customer_id}"
        headers = get_square_headers()
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if "customer" in data:
            return {"success": True, "customer": data["customer"]}
        return {"success": False, "error": "Customer not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_square_customer_by_email(email: str) -> Dict[str, Any]:
    """Search for a Square customer by email."""
    try:
        url = f"{get_square_base_url()}/v2/customers/search"
        headers = get_square_headers()
        payload = {"query": {"filter": {"email_address": {"exact": email}}}}
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()
        customers = data.get("customers", [])
        if customers:
            return {"success": True, "customer": customers[0], "customer_id": customers[0]["id"]}
        return {"success": False, "error": "Customer not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def update_square_customer(customer_id: str, **kwargs) -> Dict[str, Any]:
    """Update a customer in Square."""
    try:
        url = f"{get_square_base_url()}/v2/customers/{customer_id}"
        headers = get_square_headers()
        response = requests.put(url, json=kwargs, headers=headers, timeout=10)
        data = response.json()
        if "customer" in data:
            return {"success": True, "customer": data["customer"]}
        return {"success": False, "error": str(data.get("errors", "Unknown error"))}
    except Exception as e:
        logger.error(f"Error updating customer: {str(e)}")
        return {"success": False, "error": str(e)}

# --- Card Operations ---

def create_card_on_file(source_id: str, customer_id: str, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a card on file using Square Cards API.
    This saves a payment method for future use and returns a card_id that can be used for subscriptions.
    """
    try:
        if not customer_id:
            raise ValueError("customer_id is required to create a card on file")
        
        if not source_id or not source_id.strip():
            raise ValueError("source_id is required and cannot be blank")
        
        url = f"{get_square_base_url()}/v2/cards"
        headers = get_square_headers()
        
        # Generate idempotency key if not provided
        if not idempotency_key:
            import uuid
            idempotency_key = str(uuid.uuid4())
        
        payload = {
            "idempotency_key": idempotency_key,
            "source_id": source_id,
            "card": {
                "customer_id": customer_id
            }
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code not in [200, 201]:
            error_text = response.text
            logger.error(f"Square Create Card API error: {response.status_code} - {error_text}")
            try:
                error_data = response.json()
                errors = error_data.get("errors", [])
                error_messages = [error.get("detail", error.get("code", "Unknown error")) for error in errors]
                return {
                    "success": False,
                    "error": ', '.join(error_messages),
                    "card_id": None,
                    "http_status": response.status_code,
                    "errors": errors
                }
            except:
                return {
                    "success": False,
                    "error": error_text,
                    "card_id": None,
                    "http_status": response.status_code
                }
        
        data = response.json()
        
        if "card" in data:
            card = data["card"]
            card_id = card.get("id")
            card_customer_id = card.get("customer_id")
            
            # Verify association
            if not card_customer_id or card_customer_id != customer_id:
                logger.error(f"CRITICAL: Card {card_id} created but not associated with customer {customer_id}")
                return {
                    "success": False,
                    "error": f"Card created but not associated with customer. Expected {customer_id}, got {card_customer_id}",
                    "card_id": None
                }
            
            return {
                "success": True,
                "card_id": card_id,
                "last_4": card.get("last_4"),
                "brand": card.get("card_brand"),
                "exp_month": card.get("exp_month"),
                "exp_year": card.get("exp_year"),
                "customer_id": card_customer_id,
                "card": card
            }
        return {"success": False, "error": "No card data in response"}
            
    except Exception as e:
        logger.error(f"Error creating card on file: {str(e)}")
        return {"success": False, "error": str(e), "card_id": None}

def get_customer_cards(customer_id: str) -> Dict[str, Any]:
    """Fetch all cards on file for a customer."""
    try:
        # Try the newer Cards Search API first
        url = f"{get_square_base_url()}/v2/cards/search"
        headers = get_square_headers()
        
        payload = {
            "query": {
                "filter": {
                    "customer_id": {
                        "exact": customer_id
                    }
                }
            }
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code not in [200, 201]:
            return {"success": False, "error": response.text, "cards": []}
        
        data = response.json()
        return {"success": True, "cards": data.get("cards", [])}
    except Exception as e:
        return {"success": False, "error": str(e)}

def disable_card(card_id: str) -> Dict[str, Any]:
    """Disable a card on file in Square."""
    try:
        url = f"{get_square_base_url()}/v2/cards/{card_id}/disable"
        headers = get_square_headers()
        response = requests.post(url, headers=headers, timeout=10)
        data = response.json()
        if "card" in data:
            return {"success": True, "card": data["card"]}
        return {"success": False, "error": str(data.get("errors", "Unknown error"))}
    except Exception as e:
        logger.error(f"Error disabling card: {str(e)}")
        return {"success": False, "error": str(e)}

# --- Catalog Operations ---

def get_catalog_objects(types: Optional[List[str]] = None) -> Dict[str, Any]:
    """Fetch catalog objects from Square."""
    try:
        url = f"{get_square_base_url()}/v2/catalog/list"
        headers = get_square_headers()
        params = {"types": ",".join(types)} if types else {}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        return {"errors": [{"detail": str(e)}]}

def get_subscription_plans() -> Dict[str, Any]:
    """Fetch all subscription plans from Square Catalog."""
    try:
        url = f"{get_square_base_url()}/v2/catalog/list"
        headers = get_square_headers()
        params = {"types": "SUBSCRIPTION_PLAN,SUBSCRIPTION_PLAN_VARIATION"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        plans = []
        variations_by_plan = {}
        
        for obj in data.get("objects", []):
            if obj["type"] == "SUBSCRIPTION_PLAN_VARIATION":
                var_data = obj["subscription_plan_variation_data"]
                plan_id = var_data["subscription_plan_id"]
                if plan_id not in variations_by_plan: variations_by_plan[plan_id] = []
                variations_by_plan[plan_id].append({
                    "id": obj["id"],
                    "name": var_data.get("name"),
                    "phases": var_data.get("phases", [])
                })
        
        for obj in data.get("objects", []):
            if obj["type"] == "SUBSCRIPTION_PLAN":
                plan_id = obj["id"]
                plans.append({
                    "id": plan_id,
                    "name": obj["subscription_plan_data"].get("name"),
                    "variations": variations_by_plan.get(plan_id, [])
                })
        
        return {"success": True, "plans": plans}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Subscription Operations ---

def create_subscription(
    customer_id: str,
    location_id: str,
    plan_variation_id: str,
    card_id: str,
    idempotency_key: Optional[str] = None,
    start_date: Optional[str] = None
) -> Dict[str, Any]:
    """Create a subscription in Square."""
    try:
        url = f"{get_square_base_url()}/v2/subscriptions"
        headers = get_square_headers()
        payload = {
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
            "location_id": location_id,
            "plan_variation_id": plan_variation_id,
            "customer_id": customer_id,
            "card_id": card_id
        }
        if start_date: payload["start_date"] = start_date
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        data = response.json()
        if "subscription" in data:
            return {"success": True, "subscription": data["subscription"], "subscription_id": data["subscription"]["id"]}
        
        errors = data.get("errors", [])
        return {"success": False, "error": str(errors)}
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_subscriptions(customer_id: Optional[str] = None, status: Optional[str] = None, cursor: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch active subscriptions from Square Subscriptions API.
    """
    try:
        url = f"{get_square_base_url()}/v2/subscriptions/search"
        headers = get_square_headers()
        
        payload = {"query": {"filter": {}}}
        if customer_id:
            payload["query"]["filter"]["customer_ids"] = [customer_id]
        if status:
            payload["query"]["filter"]["statuses"] = [status]
        if cursor:
            payload["cursor"] = cursor
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {"success": False, "error": response.text, "subscriptions": []}
        
        data = response.json()
        return {
            "success": True, 
            "subscriptions": data.get("subscriptions", []), 
            "cursor": data.get("cursor")
        }
    except Exception as e:
        logger.error(f"Error fetching subscriptions: {str(e)}")
        return {"success": False, "error": str(e)}

def search_subscriptions(status: Optional[str] = None) -> Dict[str, Any]:
    """
    Compatibility wrapper for admin.py using get_subscriptions.
    """
    return get_subscriptions(status=status)

def cancel_subscription(subscription_id: str) -> Dict[str, Any]:
    """Cancel a subscription in Square."""
    try:
        url = f"{get_square_base_url()}/v2/subscriptions/{subscription_id}/cancel"
        headers = get_square_headers()
        response = requests.post(url, headers=headers, timeout=10)
        data = response.json()
        if "subscription" in data:
            return {"success": True, "subscription": data["subscription"]}
        return {"success": False, "error": str(data.get("errors", "Unknown error"))}
    except Exception as e:
        return {"success": False, "error": str(e)}

def retrieve_subscription(subscription_id: str) -> Dict[str, Any]:
    """Retrieve a single subscription by ID."""
    try:
        url = f"{get_square_base_url()}/v2/subscriptions/{subscription_id}"
        headers = get_square_headers()
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if "subscription" in data:
            return {"success": True, "subscription": data["subscription"]}
        return {"success": False, "error": str(data.get("errors", "Unknown error"))}
    except Exception as e:
        return {"success": False, "error": str(e)}

def update_subscription(subscription_id: str, plan_variation_id: str) -> Dict[str, Any]:
    """Swap subscription plan in Square."""
    try:
        url = f"{get_square_base_url()}/v2/subscriptions/{subscription_id}/swap-plan"
        headers = get_square_headers()
        payload = {"new_plan_variation_id": plan_variation_id}
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()
        if "subscription" in data:
            return {"success": True, "subscription": data["subscription"]}
        return {"success": False, "error": str(data.get("errors", "Unknown error"))}
    except Exception as e:
        return {"success": False, "error": str(e)}

def update_subscription_card(subscription_id: str, card_id: str) -> Dict[str, Any]:
    """Update the payment card for a subscription in Square."""
    try:
        url = f"{get_square_base_url()}/v2/subscriptions/{subscription_id}"
        headers = get_square_headers()
        payload = {
            "subscription": {
                "card_id": card_id
            }
        }
        # Note: According to Square API, this is a PUT to update the subscription
        response = requests.put(url, json=payload, headers=headers, timeout=10)
        data = response.json()
        if "subscription" in data:
            return {"success": True, "subscription": data["subscription"]}
        return {"success": False, "error": str(data.get("errors", "Unknown error"))}
    except Exception as e:
        logger.error(f"Error updating subscription card: {str(e)}")
        return {"success": False, "error": str(e)}

def pause_subscription(subscription_id: str) -> Dict[str, Any]:
    """Pause a subscription in Square."""
    try:
        url = f"{get_square_base_url()}/v2/subscriptions/{subscription_id}/pause"
        headers = get_square_headers()
        response = requests.post(url, json={}, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        return {"errors": [{"detail": str(e)}]}

def resume_subscription(subscription_id: str) -> Dict[str, Any]:
    """Resume a subscription in Square."""
    try:
        url = f"{get_square_base_url()}/v2/subscriptions/{subscription_id}/resume"
        headers = get_square_headers()
        response = requests.post(url, json={}, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        return {"errors": [{"detail": str(e)}]}

# --- Invoice Operations ---

def get_customer_invoices(customer_id: str, location_id: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
    """Fetch invoices for a customer using robust search."""
    try:
        url = f"{get_square_base_url()}/v2/invoices/search"
        headers = get_square_headers()
        
        loc_id = location_id or SQUARE_LOCATION_ID
        
        payload = {
            "query": {
                "filter": {
                    "customer_ids": [customer_id]
                },
                "sort": {
                    "field": "INVOICE_SORT_DATE",
                    "order": "DESC"
                }
            }
        }
        
        if loc_id:
             payload["query"]["filter"]["location_ids"] = [loc_id]
        if limit:
            payload["limit"] = limit
            
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {"success": False, "error": response.text, "invoices": []}
        
        data = response.json()
        return {
            "success": True, 
            "invoices": data.get("invoices", []), 
            "errors": data.get("errors", [])
        }
    except Exception as e:
        logger.error(f"Error fetching invoices: {str(e)}")
        return {"success": False, "error": str(e)}
def search_invoices(customer_id: str, location_id: Optional[str] = None) -> Dict[str, Any]:
    """Search for invoices belonging to a specific customer using Square Invoices API."""
    try:
        url = f"{get_square_base_url()}/v2/invoices/search"
        headers = get_square_headers()
        curr_location_id = location_id or SQUARE_LOCATION_ID
        
        payload = {
            "query": {
                "filter": {
                    "location_ids": [curr_location_id],
                    "customer_ids": [customer_id]
                },
                "sort": {
                    "field": "INVOICE_SORT_DATE",
                    "order": "DESC"
                }
            }
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()
        
        if response.status_code == 200:
            return {"success": True, "invoices": data.get("invoices", [])}
        
        return {"success": False, "error": str(data.get("errors", "Unknown error fetching invoices"))}
    except Exception as e:
        logger.error(f"Error searching invoices: {str(e)}")
        return {"success": False, "error": str(e)}
