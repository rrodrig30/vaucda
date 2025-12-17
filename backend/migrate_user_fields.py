"""
Database migration script to add new user profile fields.
Run this script to migrate existing databases to the new schema.
"""
import asyncio
from sqlalchemy import text
from app.database.sqlite_session import engine


async def migrate_user_table():
    """Add new columns to users table if they don't exist."""
    async with engine.begin() as conn:
        # Check if columns exist and add them if they don't
        columns_to_add = [
            ("first_name", "VARCHAR(100)"),
            ("last_name", "VARCHAR(100)"),
            ("initials", "VARCHAR(10)"),
            ("position", "VARCHAR(50)"),
            ("specialty", "VARCHAR(50)"),
        ]

        for column_name, column_type in columns_to_add:
            try:
                # Try to add the column
                await conn.execute(
                    text(f"ALTER TABLE users ADD COLUMN {column_name} {column_type};")
                )
                print(f"✓ Added column: {column_name}")
            except Exception as e:
                # Column likely already exists
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"  Column {column_name} already exists, skipping")
                else:
                    print(f"✗ Error adding column {column_name}: {e}")

        print("\n✓ Migration completed successfully!")


if __name__ == "__main__":
    print("Starting database migration...")
    print("Adding new user profile fields to users table\n")
    asyncio.run(migrate_user_table())
