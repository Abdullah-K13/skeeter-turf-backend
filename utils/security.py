from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
import os

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    default="pbkdf2_sha256",
    deprecated="auto",
)

SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkey")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

def hash_password(password: str) -> str:
    if password is None:
        password = ""
    return pwd_context.hash(str(password))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if plain_password is None:
        plain_password = ""
    return pwd_context.verify(str(plain_password), hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=6)):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
