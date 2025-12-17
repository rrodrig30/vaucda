#!/usr/bin/env python3
"""
Create an admin user for VAUCDA
Usage: python scripts/create_admin_user.py
"""
import asyncio
import sys
import os
from getpass import getpass

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database.sqlite_session import AsyncSessionLocal, init_db
from app.database.sqlite_models import User
from app.core.security import get_password_hash
import uuid
from datetime import datetime


async def create_admin_user():
    """Create an admin user interactively."""
    print("=" * 60)
    print("VAUCDA Admin User Creation")
    print("=" * 60)
    print()

    # Initialize database
    print("Initializing database...")
    await init_db()
    print("Database initialized.")
    print()

    # Get user input
    email = input("Enter admin email: ").strip()
    if not email:
        print("Error: Email is required")
        return

    full_name = input("Enter full name: ").strip()

    password = getpass("Enter password: ")
    if len(password) < 8:
        print("Error: Password must be at least 8 characters")
        return

    password_confirm = getpass("Confirm password: ")
    if password != password_confirm:
        print("Error: Passwords do not match")
        return

    # Create user
    async with AsyncSessionLocal() as session:
        try:
            # Check if user already exists
            from sqlalchemy import select
            result = await session.execute(
                select(User).where(User.email == email)
            )
            existing_user = result.scalar_one_or_none()

            if existing_user:
                print(f"Error: User with email {email} already exists")
                return

            # Create new admin user
            admin_user = User(
                user_id=str(uuid.uuid4()),
                email=email,
                hashed_password=get_password_hash(password),
                full_name=full_name,
                role="admin",
                is_active=True,
                created_at=datetime.utcnow()
            )

            session.add(admin_user)
            await session.commit()

            print()
            print("=" * 60)
            print("✓ Admin user created successfully!")
            print("=" * 60)
            print(f"Email: {email}")
            print(f"Name: {full_name}")
            print(f"Role: admin")
            print(f"User ID: {admin_user.user_id}")
            print()
            print("You can now login with these credentials.")

        except Exception as e:
            print(f"Error creating admin user: {str(e)}")
            await session.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(create_admin_user())
