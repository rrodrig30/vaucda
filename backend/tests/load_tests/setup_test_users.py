#!/usr/bin/env python3
"""
Setup test users for load testing

Creates 100 test users with credentials:
- Email: loadtest{1-100}@va.gov
- Password: LoadTest123!@#

Usage:
    python tests/load_tests/setup_test_users.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

from app.database.sqlite_session import get_async_session, init_db
from app.database.sqlite_models import User
from app.core.security import hash_password
from sqlalchemy import select
import uuid


async def create_test_users(num_users=100):
    """Create test users for load testing"""

    # Initialize database
    await init_db()

    async for session in get_async_session():
        created = 0
        skipped = 0

        for i in range(1, num_users + 1):
            email = f"loadtest{i}@va.gov"

            # Check if user exists
            result = await session.execute(
                select(User).where(User.email == email)
            )
            existing = result.scalar_one_or_none()

            if existing:
                print(f"User {email} already exists, skipping...")
                skipped += 1
                continue

            # Create user
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                hashed_password=hash_password("LoadTest123!@#"),
                full_name=f"Load Test User {i}",
                role="provider",  # Regular provider role
                is_active=True
            )

            session.add(user)
            created += 1

            if i % 10 == 0:
                print(f"Created {i}/{num_users} users...")

        await session.commit()

        print(f"\n{'='*60}")
        print(f"Test User Setup Complete")
        print(f"{'='*60}")
        print(f"Created: {created} users")
        print(f"Skipped: {skipped} users (already exist)")
        print(f"Total: {num_users} users")
        print(f"{'='*60}")
        print(f"\nCredentials:")
        print(f"  Email: loadtest{{1-{num_users}}}@va.gov")
        print(f"  Password: LoadTest123!@#")
        print(f"{'='*60}\n")


async def cleanup_test_users():
    """Remove all test users"""

    async for session in get_async_session():
        result = await session.execute(
            select(User).where(User.email.like("loadtest%@va.gov"))
        )
        users = result.scalars().all()

        for user in users:
            await session.delete(user)

        await session.commit()

        print(f"Deleted {len(users)} test users")


async def verify_test_users():
    """Verify test users exist and can authenticate"""

    from app.core.security import verify_password

    async for session in get_async_session():
        result = await session.execute(
            select(User).where(User.email == "loadtest1@va.gov")
        )
        user = result.scalar_one_or_none()

        if not user:
            print("❌ Test user loadtest1@va.gov not found")
            return False

        if not verify_password("LoadTest123!@#", user.hashed_password):
            print("❌ Password verification failed")
            return False

        print("✅ Test users verified successfully")
        return True


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Manage load test users")
    parser.add_argument(
        "command",
        choices=["create", "cleanup", "verify"],
        help="Command to execute"
    )
    parser.add_argument(
        "--num-users",
        type=int,
        default=100,
        help="Number of users to create (default: 100)"
    )

    args = parser.parse_args()

    if args.command == "create":
        await create_test_users(args.num_users)
    elif args.command == "cleanup":
        await cleanup_test_users()
    elif args.command == "verify":
        await verify_test_users()


if __name__ == "__main__":
    asyncio.run(main())
