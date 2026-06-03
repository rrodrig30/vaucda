#!/usr/bin/env python3
"""
Migration script to add task-specific LLM columns to user_preferences table.
Run this if you get errors about missing columns.

Usage: python -m database.migrations.add_task_llm_columns
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


def run_migration():
    """Add task-specific LLM columns to user_preferences table."""
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
    print(f"Existing columns: {existing_columns}")

    # Define columns to add
    columns_to_add = [
        # OCR LLM Configuration
        ("ocr_llm_provider", "VARCHAR(50)"),
        ("ocr_llm_model", "VARCHAR(100)"),
        ("ocr_llm_temperature", "FLOAT"),
        ("ocr_llm_max_tokens", "INTEGER"),
        # Stage 1 LLM Configuration
        ("stage1_llm_provider", "VARCHAR(50)"),
        ("stage1_llm_model", "VARCHAR(100)"),
        ("stage1_llm_temperature", "FLOAT"),
        ("stage1_llm_max_tokens", "INTEGER"),
        # Stage 2 LLM Configuration
        ("stage2_llm_provider", "VARCHAR(50)"),
        ("stage2_llm_model", "VARCHAR(100)"),
        ("stage2_llm_temperature", "FLOAT"),
        ("stage2_llm_max_tokens", "INTEGER"),
        ("stage2_use_rag", "BOOLEAN"),
        ("stage2_use_graphrag", "BOOLEAN"),
        ("stage2_rag_top_k", "INTEGER"),
    ]

    added_count = 0
    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
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
