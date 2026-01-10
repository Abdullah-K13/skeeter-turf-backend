from sqlalchemy import Column, Integer, String, Float, TIMESTAMP, text, ForeignKey, Date, Boolean
from db.init import Base

class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    id = Column(Integer, primary_key=True, index=True)
    plan_name = Column(String(100))
    plan_cost = Column(Float)
    plan_variation_id = Column(String(255)) # Square Variation ID
    plan_description = Column(String(500))

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    amount = Column(Float)
    status = Column(String(50)) # PAID, FAILED, PENDING
    square_transaction_id = Column(String(255))
    created_at = Column(TIMESTAMP, server_default=text("NOW()"))

class PaymentMethod(Base):
    __tablename__ = "payment_methods"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    square_card_id = Column(String(255), nullable=False)
    last_4_digits = Column(String(4), nullable=False)
    card_brand = Column(String(50))
    exp_month = Column(Integer)
    exp_year = Column(Integer)
    is_default = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=text("NOW()"))

class SubscriptionLog(Base):
    __tablename__ = "subscription_logs"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    subscription_id = Column(String(255), nullable=False)
    action = Column(String(50), nullable=False) # "PAUSE", "RESUME", "CANCEL", "ACTIVATE"
    effective_date = Column(Date, nullable=True)
    created_at = Column(TIMESTAMP, server_default=text("NOW()"))

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    square_invoice_id = Column(String(255), unique=True, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    subscription_id = Column(String(255), nullable=True) # Square Subscription ID
    amount = Column(Float, nullable=False)
    status = Column(String(50), default="PENDING") # PAID, UNPAID, CANCELLED, etc.
    due_date = Column(Date, nullable=True)
    public_url = Column(String(500), nullable=True) # Link to Square hosted invoice
    created_at = Column(TIMESTAMP, server_default=text("NOW()"))
