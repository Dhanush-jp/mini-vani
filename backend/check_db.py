from database.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    print("Columns in import_audits:")
    try:
        rows = conn.execute(text("DESCRIBE import_audits")).fetchall()
        for row in rows:
            print(f" - {row[0]} ({row[1]})")
    except Exception as e:
        print(f"Error describing table: {e}")
