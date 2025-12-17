#!/usr/bin/env python3
"""
Create test user in the database
"""
import asyncio
import uuid
from datetime import datetime
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database.sqlite_models import Base, User

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_test_user():
    """Create a test user in the database."""

    # Create engine and session
    engine = create_async_engine(
        "sqlite+aiosqlite:///./vaucda.db",
        echo=False
    )

    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        # Create test user
        hashed_password = pwd_context.hash("testpass")

        test_user = User(
            user_id=str(uuid.uuid4()),
            email="testuser",
            hashed_password=hashed_password,
            full_name="Test User",
            role="user",
            is_active=True,
            created_at=datetime.utcnow()
        )

        session.add(test_user)
        await session.commit()

        print(f"✓ Test user created:")
        print(f"  Username: testuser")
        print(f"  Password: testpass")
        print(f"  User ID: {test_user.user_id}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_test_user())
