from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from db.init import get_db
from models.user import Customer
import os

security = HTTPBearer()

SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkey")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_db_user(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user.get("id")
    user = db.query(Customer).filter(Customer.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
