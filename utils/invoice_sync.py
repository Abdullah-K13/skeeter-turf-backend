"""Pull a customer's Square invoices into the local invoices table.

Extracted from the admin sync-invoices endpoint so the same upsert can run from
anywhere. Before this, the ONLY thing that ever created an Invoice row was an admin
clicking "View Invoices" on one customer in the dropdown - no scheduler, no webhook,
no backfill. Customers nobody opened simply had no invoice history locally, however
many paid invoices Square held for them.
"""
import logging
from datetime import datetime
from typing import Any, Dict

from sqlalchemy.orm import Session

from models.subscription import Invoice
from models.user import Customer
from utils.square_client import search_invoices

try:
    # Some backends give Invoice a ForeignKey("properties.id"). SQLAlchemy resolves that
    # when the mapper configures, so the table must be registered even when this module
    # is used outside the app (a script run via docker exec, say, where init_db and the
    # routers that import Property never run). Absent elsewhere, which is fine.
    from models import property as _property  # noqa: F401
except ImportError:
    pass

logger = logging.getLogger(__name__)


def _amount_of(sq_inv: Dict[str, Any]) -> float:
    """Square puts the figure in payment_requests, falling back to the next payment."""
    amount_data = {}
    requests_ = sq_inv.get("payment_requests") or []
    if requests_:
        amount_data = requests_[0].get("computed_amount_money") or {}
    if not amount_data.get("amount") and sq_inv.get("next_payment_amount_money"):
        amount_data = sq_inv["next_payment_amount_money"]
    return float(amount_data.get("amount", 0)) / 100.0


def _due_date_of(sq_inv: Dict[str, Any]):
    raw = sq_inv.get("scheduled_at") or sq_inv.get("created_at") or datetime.now().isoformat()
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        logger.warning(f"Unparseable invoice date {raw!r}; falling back to today")
        return datetime.now().date()


def sync_invoices_for_customer(db: Session, customer: Customer, commit: bool = True) -> Dict[str, Any]:
    """Upsert every Square invoice for this customer. Returns counts; raises nothing."""
    if not customer or not customer.square_customer_id:
        return {"success": False, "error": "Customer has no Square customer id", "synced": 0, "updated": 0}

    res = search_invoices(customer.square_customer_id)
    if not res.get("success"):
        return {"success": False, "error": res.get("error"), "synced": 0, "updated": 0}

    synced = updated = 0
    for sq_inv in res.get("invoices", []):
        inv_id = sq_inv.get("id")
        if not inv_id:
            continue

        existing = db.query(Invoice).filter(Invoice.square_invoice_id == inv_id).first()
        amount = _amount_of(sq_inv)

        if existing:
            existing.status = sq_inv.get("status")
            existing.public_url = sq_inv.get("public_url")
            existing.amount = amount
            updated += 1
        else:
            db.add(Invoice(
                square_invoice_id=inv_id,
                customer_id=customer.id,
                subscription_id=sq_inv.get("subscription_id"),
                amount=amount,
                status=sq_inv.get("status"),
                due_date=_due_date_of(sq_inv),
                public_url=sq_inv.get("public_url"),
            ))
            synced += 1

    if commit:
        db.commit()
    return {"success": True, "synced": synced, "updated": updated}
