from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Neue Spalte für PW-Reset
    try:
        conn.execute(text("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE;
        """))
        conn.commit()
        print("✅ Spalte 'must_change_password' hinzugefügt")
    except Exception as e:
        print(f"Info: {e}")
    
    # Alle auf TRUE setzen für ersten Login
    conn.execute(text("""
        UPDATE users 
        SET must_change_password = TRUE 
        WHERE email != 'admin@seda24.de';
    """))
    conn.commit()
    print("✅ Alle müssen PW beim ersten Login ändern")
