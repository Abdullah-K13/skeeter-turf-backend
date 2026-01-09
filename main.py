from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db.init import init_db
from dotenv import load_dotenv
import os

load_dotenv()

from routers import auth, payment, admin

app = FastAPI(title="Skeeter Backend")

# Configure CORS
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "https://api1.protownnetwork.com",
    "https://darkgoldenrod-marten-447328.hostingersite.com",
]

app.add_middleware(
    CORSMiddleware,
    # allow_origins=origins,
    allow_origin_regex=".*",  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# @app.on_event("startup")
# def startup():
#     init_db()

# Include Routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(payment.router, prefix="/payments", tags=["Payments"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "Skeeter Backend running successfully"}
