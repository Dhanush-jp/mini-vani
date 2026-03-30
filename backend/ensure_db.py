from database.session import engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("db_fix")

def fix_import_audits():
    columns_to_add = [
        ("status", "ENUM('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED') NOT NULL DEFAULT 'PENDING'"),
        ("total_rows", "INT NOT NULL DEFAULT 0"),
        ("created", "INT NOT NULL DEFAULT 0"),
        ("updated", "INT NOT NULL DEFAULT 0"),
        ("skipped", "INT NOT NULL DEFAULT 0"),
        ("failed", "INT NOT NULL DEFAULT 0"),
        ("errors_json", "TEXT NULL")
    ]
    
    with engine.connect() as conn:
        # Get existing columns
        existing = [row[0] for row in conn.execute(text("DESCRIBE import_audits")).fetchall()]
        
        for col_name, col_def in columns_to_add:
            if col_name not in existing:
                logger.info(f"Adding column {col_name} to import_audits")
                try:
                    conn.execute(text(f"ALTER TABLE import_audits ADD COLUMN {col_name} {col_def}"))
                    conn.commit()
                except Exception as e:
                    logger.error(f"Failed to add column {col_name}: {e}")
            else:
                logger.info(f"Column {col_name} already exists in import_audits")

if __name__ == "__main__":
    fix_import_audits()
    print("Database schema check complete.")
