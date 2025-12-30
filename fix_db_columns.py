from db.init import engine
from sqlalchemy import text

def update_schema():
    print("Updating customers table schema...")
    with engine.connect() as conn:
        # Add missing columns for Square integration
        queries = [
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS square_customer_id VARCHAR(255)",
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS square_subscription_id VARCHAR(255)",
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS subscription_active BOOLEAN DEFAULT FALSE",
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50)",
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS plan_id VARCHAR(50)",
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS plan_variation_id VARCHAR(255)"
        ]
        
        for query in queries:
            try:
                conn.execute(text(query))
                print(f"Executed: {query}")
            except Exception as e:
                print(f"Error executing {query}: {e}")
        
        conn.commit()
    print("Schema update complete.")

if __name__ == "__main__":
    update_schema()
