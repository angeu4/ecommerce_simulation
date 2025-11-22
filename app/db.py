import asyncio

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.constants import REQUEST_ID_SYSTEM
from app.core.logging_setup import get_logger

logger = get_logger(__name__)

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_db_and_tables():
    """
    Creates database tables asynchronously.

    This function is idempotent and will only create the database tables if they do not already exist.
    It will retry up to 10 times with a 2 second delay in between retries if an exception occurs.
    If all retries fail, it will raise a RuntimeError with a message indicating DB initialization failed.

    :return: None
    :raises RuntimeError: If the DB initialization fails after 10 retries
    """
    
    import app.models  # noqa
    logger.info("Initializing database schema...", extra={"request_id": REQUEST_ID_SYSTEM})

    for _ in range(10):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.drop_all)
                await conn.run_sync(SQLModel.metadata.create_all)
            
            logger.info("Database tables created successfully", extra={"request_id": REQUEST_ID_SYSTEM})
            return
        except Exception:
            await asyncio.sleep(2)

    raise RuntimeError("DB initialization failed")
