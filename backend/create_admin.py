"""Create admin user for VAUCDA"""
import asyncio
import uuid
from datetime import datetime
from sqlalchemy import select
from app.database.sqlite_session import AsyncSessionLocal
from app.database.sqlite_models import User, UserPreferences
from app.core.security import get_password_hash


async def create_admin():
    """Create admin user if not exists"""
    async with AsyncSessionLocal() as db:
        # Check if admin exists
        result = await db.execute(
            select(User).where(User.email == "admin@vaucda.va.gov")
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Admin user already exists: {existing.email}")
            return

        # Create admin user
        admin = User(
            user_id=str(uuid.uuid4()),
            email="admin@vaucda.va.gov",
            hashed_password=get_password_hash("Admin123!"),
            full_name="VAUCDA Administrator",
            role="admin",
            is_active=True,
            created_at=datetime.utcnow()
        )

        db.add(admin)
        await db.commit()
        await db.refresh(admin)

        # Create preferences
        prefs = UserPreferences(
            user_id=admin.user_id,
            default_llm="ollama",
            default_model="llama3.1:8b",
            llm_temperature=0.3,
            llm_max_tokens=4000,
            llm_top_p=0.9
        )

        db.add(prefs)
        await db.commit()

        print(f"✓ Admin user created successfully!")
        print(f"  Email: {admin.email}")
        print(f"  Password: Admin123!")
        print(f"  Role: {admin.role}")


if __name__ == "__main__":
    asyncio.run(create_admin())
