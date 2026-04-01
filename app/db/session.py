"""
Database Session — Async SQLAlchemy session factory.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from contextlib import asynccontextmanager
import os

from app.utils.logger import get_logger

logger = get_logger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5432/memory_agent"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("ENVIRONMENT") == "development",
    pool_size=10,
    max_overflow=20,
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_async_session():
    """Context manager that provides a DB session and handles commit/rollback."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"DB session error: {e}")
            raise


async def init_db():
    """Create all tables on startup if they don't exist."""
    from app.db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized ✓")
