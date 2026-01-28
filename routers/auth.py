from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional, List
from sqlalchemy.orm import Session
from db.init import get_db
from models.user import Customer, Admin
from utils.security import hash_password, verify_password, create_access_token
from pydantic import BaseModel, EmailStr

router = APIRouter()

class SignUpRequest(BaseModel):
    firstName: str
    lastName: str
    email: EmailStr
    phone: str
    password: str
    address: str
    city: str
    zip: str
    plan: str
    planVariationId: str
    skeetermanNumber: str
    addons: Optional[List[str]] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

@router.post("/signup")
def signup(request: SignUpRequest, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(Customer).filter(Customer.email == request.email).first()
    
    if existing_user:
        # Check if they are fully registered (have Square ID)
        if existing_user.square_customer_id:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # If no Square ID, they failed previous signup. Update their details.
        existing_user.first_name = request.firstName
        existing_user.last_name = request.lastName
        existing_user.phone_number = request.phone
        existing_user.password_hash = hash_password(request.password)
        existing_user.address = request.address
        existing_user.city = request.city
        existing_user.zip_code = request.zip
        existing_user.plan_id = request.plan
        existing_user.plan_variation_id = request.planVariationId
        existing_user.skeeterman_number = request.skeetermanNumber
        existing_user.selected_addons = request.addons
        
        db.commit()
        db.refresh(existing_user)
        new_customer = existing_user
    else:
        new_customer = Customer(
            first_name=request.firstName,
            last_name=request.lastName,
            email=request.email,
            phone_number=request.phone,
            password_hash=hash_password(request.password),
            address=request.address,
            city=request.city,
            zip_code=request.zip,
            plan_id=request.plan,
            plan_variation_id=request.planVariationId,
            skeeterman_number=request.skeetermanNumber,
            selected_addons=request.addons
        )
        
        db.add(new_customer)
        db.commit()
        db.refresh(new_customer)
    
    # Generate token so they are logged in after signup
    access_token = create_access_token(data={"sub": new_customer.email, "id": new_customer.id})
    
    return {
        "message": "User created successfully", 
        "user_id": new_customer.id,
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": new_customer.id,
            "email": new_customer.email,
            "firstName": new_customer.first_name,
            "lastName": new_customer.last_name,
            "role": "customer"
        }
    }

@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(Customer).filter(Customer.email == request.email).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    access_token = create_access_token(data={"sub": user.email, "id": user.id})
    return {"access_token": access_token, "token_type": "bearer", "user": {
        "id": user.id,
        "email": user.email,
        "firstName": user.first_name,
        "lastName": user.last_name,
        "role": "customer"
    }}

@router.post("/admin/login")
def admin_login(request: LoginRequest, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.email == request.email).first()
    if not admin or not verify_password(request.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    access_token = create_access_token(data={"sub": admin.email, "id": admin.id, "role": "admin"})
    return {"access_token": access_token, "token_type": "bearer", "user": {
        "id": admin.id,
        "email": admin.email,
        "name": admin.name,
        "role": "admin"
    }}
