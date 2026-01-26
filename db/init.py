from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in environment (.env)")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    # Import models here to register them with Base
    from models import user, subscription
    Base.metadata.create_all(bind=engine)
    seed_db()

def seed_db():
    from models.subscription import SubscriptionPlan
    from models.subscription_schedule import SubscriptionPlanSchedule
    from models.user import Admin
    from utils.security import hash_password
    db = SessionLocal()
    try:
        # Database seeding with admins
        admin_data = [
            {"name": "Admin User", "email": "admin@skeeter.com", "password": "admin123", "phone": "1234567890"},
            {"name": "Admin Two", "email": "admin2@skeeter.com", "password": "appleapple22", "phone": "1234567891"},
            {"name": "Admin Three", "email": "admin3@skeeter.com", "password": "appleapple33", "phone": "1234567892"},
        ]
        
        for data in admin_data:
            if not db.query(Admin).filter(Admin.email == data["email"]).first():
                new_admin = Admin(
                    name=data["name"],
                    email=data["email"],
                    password_hash=hash_password(data["password"]),
                    phone_number=data["phone"]
                )
                db.add(new_admin)
        
        # Seed subscription plan schedules
        # Turf: January to November ($100)
        # Mosquito: March to November ($80)
        # Ground Control: January and February ($150)
        plan_schedules = [
            {"plan_name": "Turf", "start_month": 1, "end_month": 11},         # Jan-Nov
            {"plan_name": "Mosquito", "start_month": 3, "end_month": 11},     # Mar-Nov
            {"plan_name": "Ground Control", "start_month": 1, "end_month": 2} # Jan-Feb
        ]
        
        for schedule in plan_schedules:
            existing = db.query(SubscriptionPlanSchedule).filter(
                SubscriptionPlanSchedule.plan_name == schedule["plan_name"]
            ).first()
            if not existing:
                # Try to find the matching plan in subscription_plans table
                plan = db.query(SubscriptionPlan).filter(
                    SubscriptionPlan.plan_name.ilike(f"%{schedule['plan_name']}%")
                ).first()
                
                new_schedule = SubscriptionPlanSchedule(
                    plan_id=plan.id if plan else None,
                    plan_name=schedule["plan_name"],
                    start_month=schedule["start_month"],
                    end_month=schedule["end_month"]
                )
                db.add(new_schedule)
            
        db.commit()
    finally:
        db.close()

