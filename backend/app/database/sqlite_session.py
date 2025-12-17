"""
SQLite database session management with async support
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.config import settings
from app.database.sqlite_models import Base


# Create async engine
engine = create_async_engine(
    settings.SQLITE_DATABASE_URL,
    echo=settings.SQLITE_ECHO,
    poolclass=NullPool,  # SQLite doesn't support connection pooling well
    connect_args={"check_same_thread": False}  # Allow SQLite to work with async
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database sessions.
    Use in FastAPI endpoints with Depends(get_db).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
