#!/usr/bin/env python3
"""
Migration script to add user-controllable num_ctx columns to user_preferences table.

Adds nullable INTEGER columns that allow users to override the model's lookup-table
context window per task. NULL means "use the model's table value, or DEFAULT_CONTEXT_SIZE
(125000) if the model is unknown."

Columns added:
  - llm_num_ctx           (legacy/global override)
  - stage1_llm_num_ctx    (Stage 1 note generation)
  - stage2_llm_num_ctx    (Stage 2 Assessment & Plan)
  - ocr_llm_num_ctx       (OCR vision model)

Idempotent: re-running this script will not error if columns already exist.

Usage: python -m database.migrations.add_num_ctx_columns
"""
import sqlite3
import os
from pathlib import Path

# Default SQLite database path
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "vaucda.db"


def get_db_path():
    """Get database path from environment or default."""
    db_url = os.environ.get("SQLITE_DATABASE_URL", "")
    if db_url.startswith("sqlite+aiosqlite:///"):
        # Remove the prefix
        path = db_url.replace("sqlite+aiosqlite:///", "")
        # Handle the extra slash for absolute paths
        if path.startswith("/"):
            return path
        return path
    return str(DEFAULT_DB_PATH)


def column_exists(cursor, table_name, column_name):
    """Check if a column already exists on a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def run_migration():
    """Add user-controllable num_ctx columns to user_preferences table."""
    db_path = get_db_path()
    print(f"Database path: {db_path}")

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        print("Database will be created automatically when backend starts.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(user_preferences)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    print(f"Existing columns: {sorted(existing_columns)}")

    # Define columns to add (all nullable; NULL means defer to lookup table)
    columns_to_add = [
        ("llm_num_ctx", "INTEGER"),
        ("stage1_llm_num_ctx", "INTEGER"),
        ("stage2_llm_num_ctx", "INTEGER"),
        ("ocr_llm_num_ctx", "INTEGER"),
    ]

    added_count = 0
    for col_name, col_type in columns_to_add:
        if not column_exists(cursor, "user_preferences", col_name):
            try:
                sql = f"ALTER TABLE user_preferences ADD COLUMN {col_name} {col_type}"
                cursor.execute(sql)
                print(f"Added column: {col_name}")
                added_count += 1
            except sqlite3.OperationalError as e:
                print(f"Error adding {col_name}: {e}")
        else:
            print(f"Column already exists: {col_name}")

    conn.commit()
    conn.close()

    print(f"\nMigration complete. Added {added_count} new columns.")


if __name__ == "__main__":
    run_migration()
