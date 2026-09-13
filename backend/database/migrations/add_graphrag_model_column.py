#!/usr/bin/env python3
"""
Migration: add the graphrag_llm_model column to user_preferences.

Lets the GraphRAG build/retrieval model be selected from the Settings page
instead of only via the GRAPHRAG_LLM_MODEL env var. NULL means "use the
.env default (GRAPHRAG_LLM_MODEL)".

Idempotent: re-running will not error if the column already exists.

Usage: python -m database.migrations.add_graphrag_model_column
"""
import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "vaucda.db"


def get_db_path():
    db_url = os.environ.get("SQLITE_DATABASE_URL", "")
    if db_url.startswith("sqlite+aiosqlite:///"):
        return db_url.replace("sqlite+aiosqlite:///", "")
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

    if column_exists(cur, "user_preferences", "graphrag_llm_model"):
        print("Column already exists: graphrag_llm_model")
        conn.close()
        return

    # Nullable, no default: NULL defers to the .env GRAPHRAG_LLM_MODEL.
    cur.execute(
        "ALTER TABLE user_preferences ADD COLUMN graphrag_llm_model VARCHAR(100)"
    )
    conn.commit()
    print("Added column: graphrag_llm_model (NULL -> env GRAPHRAG_LLM_MODEL)")
    conn.close()


if __name__ == "__main__":
    run_migration()
