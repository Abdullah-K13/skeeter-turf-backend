from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from models.subscription import ItemVariation

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def check_addons():
    print("--- Checking Add-ons in DB ---")
    addons = db.query(ItemVariation).filter(ItemVariation.item_type == "ADDON").all()
    print(f"Found {len(addons)} add-ons.")
    for addon in addons:
        print(f" - {addon.name}: ${addon.price}")

if __name__ == "__main__":
    check_addons()
