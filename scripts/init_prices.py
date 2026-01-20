from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def update_addon_prices():
    if not DATABASE_URL:
        print("DATABASE_URL not found.")
        return

    engine = create_engine(DATABASE_URL)
    
    with engine.begin() as conn:
        # Set all addons to 20 by default
        conn.execute(text("UPDATE item_variations SET price = 20.0 WHERE item_type = 'ADDON';"))
        
        # Set Mole Package to 80
        conn.execute(text("UPDATE item_variations SET price = 80.0 WHERE name = 'Mole Package' AND item_type = 'ADDON';"))
        
        print("Addon prices initialized.")

if __name__ == "__main__":
    update_addon_prices()
