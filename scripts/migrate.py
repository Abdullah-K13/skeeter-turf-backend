from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def migrate():
    if not DATABASE_URL:
        print("DATABASE_URL not found.")
        return

    engine = create_engine(DATABASE_URL)
    
    print("Checking for missing columns...")
    
    columns_to_add = [
        ("order_template_id", "VARCHAR(255)", "customers"),
        ("failed_payment_attempts", "INTEGER DEFAULT 0", "customers"),
        ("price", "FLOAT DEFAULT 0.0", "item_variations")
    ]
    
    for col_name, col_type, table_name in columns_to_add:
        with engine.begin() as conn: 
            try:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type};"))
                print(f"Added column '{col_name}' to '{table_name}' table.")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print(f"Column '{col_name}' already exists.")
                else:
                    print(f"Error adding column '{col_name}': {e}")
    
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
