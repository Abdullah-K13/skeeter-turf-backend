from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Optional, List
from sqlalchemy.orm import Session
from db.init import get_db
from models.user import Customer, Admin
from utils.security import hash_password, verify_password, create_access_token, decode_token
from pydantic import BaseModel, EmailStr
import requests
import os

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

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

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

def send_brevo_email(to_email: str, subject: str, html_content: str):
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        print(f"Mock Email to {to_email}:\nSubject: {subject}\nBody: {html_content}")
        return
    
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }
    payload = {
        "sender": {"email": "hello@skeetermanturfninja.com", "name": "Skeeterman & Turf Ninja"},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"Brevo email sent successfully to {to_email}")
    except requests.exceptions.HTTPError as he:
        print(f"Brevo API Error ({he.response.status_code}): {he.response.text}")
    except Exception as e:
        print(f"Error sending email: {e}")

@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, req: Request, db: Session = Depends(get_db)):
    user = db.query(Customer).filter(Customer.email == request.email).first()
    if not user:
        # We don't want to reveal if a user exists or not
        return {"message": "If an account with that email exists, we have sent a reset link"}
    
    # Generate token valid for 15 minutes
    from datetime import timedelta
    reset_token = create_access_token(
        data={"sub": user.email, "purpose": "reset_password"},
        expires_delta=timedelta(minutes=15)
    )
    
    frontend_url = os.getenv("FRONTEND_URL")
    if not frontend_url:
        # Try to use origin if available
        origin = req.headers.get("origin")
        frontend_url = origin if origin else "http://localhost:5173"
        
    reset_url = f"{frontend_url}/reset-password?token={reset_token}"
    
    html_content = f"""
    <p>Hello {user.first_name},</p>
    <p>You requested to reset your password. Click the link below to set a new password:</p>
    <p><a href="{reset_url}">Reset My Password</a></p>
    <p>If you didn't request this, you can safely ignore this email.</p>
    """
    
    send_brevo_email(user.email, "Reset your Skeeterman Password", html_content)
    
    return {"message": "If an account with that email exists, we have sent a reset link"}

@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    payload = decode_token(request.token)
    if not payload or payload.get("purpose") != "reset_password":
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    email = payload.get("sub")
    user = db.query(Customer).filter(Customer.email == email).first()
    
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    
    user.password_hash = hash_password(request.new_password)
    db.commit()
    
    return {"message": "Password has been successfully reset"}
