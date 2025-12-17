"""
Add LLM parameter columns to user_preferences table
"""
import sqlite3
import os
import sys
from pathlib import Path

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.config import settings


def migrate():
    """Add LLM parameter columns to existing user_preferences table."""

    # Extract path from DATABASE_URL
    db_path = settings.SQLITE_DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    if db_path.startswith("./"):
        db_path = os.path.join(os.getcwd(), db_path[2:])

    print(f"Migrating database: {db_path}")

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_preferences'")
        if not cursor.fetchone():
            print("user_preferences table not found - nothing to migrate")
            return True

        # Get existing columns
        cursor.execute("PRAGMA table_info(user_preferences)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        # Add new columns if they don't exist
        new_columns = {
            "llm_temperature": "REAL",
            "llm_max_tokens": "INTEGER DEFAULT 4000",
            "llm_top_p": "REAL",
            "llm_frequency_penalty": "REAL",
            "llm_presence_penalty": "REAL"
        }

        for column_name, column_type in new_columns.items():
            if column_name not in existing_columns:
                print(f"Adding column: {column_name}")
                cursor.execute(f"ALTER TABLE user_preferences ADD COLUMN {column_name} {column_type}")
            else:
                print(f"Column {column_name} already exists - skipping")

        conn.commit()
        print("Migration completed successfully!")
        return True

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
