#!/usr/bin/env python3
"""
Migration script to add the source_format column to user_preferences.

source_format selects the source-EHR text format the user pastes /
uploads. Values: 'cprs' (default; pass-through) or 'vista' (preprocess
into CPRS layout before the existing extractors / agents see it).

Idempotent: re-running this script will not error if the column
already exists.

Usage: python -m database.migrations.add_source_format_column
"""
import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "vaucda.db"


def get_db_path():
    db_url = os.environ.get("SQLITE_DATABASE_URL", "")
    if db_url.startswith("sqlite+aiosqlite:///"):
        path = db_url.replace("sqlite+aiosqlite:///", "")
        return path
    return str(DEFAULT_DB_PATH)


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def run_migration():
    db_path = get_db_path()
    print(f"Database path: {db_path}")

    if not os.path.exists(db_path):
        print("Database not found; will be created with the new column when backend starts.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    if column_exists(cur, "user_preferences", "source_format"):
        print("Column already exists: source_format")
        conn.close()
        return

    # Default 'cprs' so existing rows behave exactly as before.
    cur.execute(
        "ALTER TABLE user_preferences "
        "ADD COLUMN source_format VARCHAR(16) NOT NULL DEFAULT 'cprs'"
    )
    conn.commit()
    print("Added column: source_format (default 'cprs')")
    conn.close()


if __name__ == "__main__":
    run_migration()
