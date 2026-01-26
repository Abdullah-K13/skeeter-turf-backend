from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, text, JSON
from db.init import Base

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    address = Column(String)
    phone_number = Column(String)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    city = Column(String)
    state = Column(String)
    zip_code = Column(String)
    skeeterman_number = Column(String(50), nullable=True)
    
    # Square Integration Fields
    square_customer_id = Column(String(255), nullable=True)
    square_subscription_id = Column(String(255), nullable=True)
    subscription_active = Column(Boolean, default=False)
    subscription_status = Column(String(50), nullable=True) # ACTIVE, PAUSED, CANCELED, etc.
    plan_id = Column(String(50), nullable=True) # mosquito, lawn, bundle
    plan_variation_id = Column(String(255), nullable=True) # Square Variation ID
    order_template_id = Column(String(255), nullable=True) # Square Order Template ID
    selected_addons = Column(JSON, nullable=True) # List of selected addon variation IDs
    failed_payment_attempts = Column(Integer, default=0)
    subscription_paused_by_schedule = Column(Boolean, default=False)  # True if paused by schedule, not manually

    
    created_at = Column(TIMESTAMP, server_default=text("NOW()"))

class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150))
    phone_number = Column(String(20))
    email = Column(String(150), unique=True)
    password_hash = Column(String)
    created_at = Column(TIMESTAMP, server_default=text("NOW()"))
