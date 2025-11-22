from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, create_engine

TEST_DB_SYNC = "sqlite:///./test_integration.db"
TEST_DB_ASYNC = "sqlite+aiosqlite:///./test_integration.db"


@pytest.fixture(autouse=True)
def patch_password_hasher(monkeypatch):
    """
    Patches the `auth.hash_password` and `auth.verify_password` functions
    with very weak test implementations that simply append "HASHED:" to
    the input password and compare the result with the hashed password.
    This is only for testing purposes and should not be used in production.
    """
    
    from app import auth

    # Very weak hash for tests only
    def fake_hash(pwd: str) -> str:
        return "HASHED:" + pwd

    def fake_verify(pwd: str, hashed: str) -> bool:
        return hashed == "HASHED:" + pwd

    monkeypatch.setattr(auth, "hash_password", fake_hash)
    monkeypatch.setattr(auth, "verify_password", fake_verify)


# ============================================================
# FORCE SETTINGS BEFORE ANY APP IMPORT
# ============================================================
@pytest.fixture(autouse=True, scope="function")
def patch_settings(monkeypatch):
    """
    Patch Settings values *directly* so FastAPI reads
    correct admin credentials on import.
    """

    monkeypatch.setenv("PYTEST_RUNNING", "1")

    # DB
    monkeypatch.setenv("DATABASE_URL", TEST_DB_ASYNC)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    # Admin creds
    monkeypatch.setenv("ADMIN_USERNAME", "XXXXX")
    monkeypatch.setenv("ADMIN_PASSWORD", "XXXXX")

    # JWT
    monkeypatch.setenv("USER_JWT_SECRET", "XXXXX")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "XXXXX")

    # Session TTL
    monkeypatch.setenv("USER_SESSION_EXPIRE_SECONDS", "3600")
    monkeypatch.setenv("ADMIN_SESSION_EXPIRE_SECONDS", "600")

    # Discounts
    monkeypatch.setenv("DISCOUNT_TTL_SECONDS", "300")
    monkeypatch.setenv("NTH_ORDER", "5")

    monkeypatch.setenv("ADMIN_API_KEY", "XXXXX")

    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "100")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")

    monkeypatch.setenv("LOG_FILE", "test.log")


@pytest.fixture(scope="function", autouse=True)
def reload_settings(patch_settings):
    """
    Reloads the `app.core.config` module after patching the Settings
    values directly. This is necessary because the Settings values are
    read on import, not when the values are patched.
    """

    import importlib

    import app.core.config as config
    importlib.reload(config)


# ============================================================
# 1) CREATE SYNC ENGINE + INITIAL SCHEMA
# ============================================================
@pytest.fixture(scope="session")
def sync_engine():
    """
    Creates a synchronous SQLAlchemy engine with the given TEST_DB_SYNC URL.
    Initializes the schema by running `SQLModel.metadata.create_all(engine)`.
    Returns the created engine.
    """
    
    engine = create_engine(TEST_DB_SYNC, echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


# ============================================================
# 2) ASYNC ENGINE
# ============================================================
@pytest_asyncio.fixture(scope="session")
async def async_engine(sync_engine):
    """
    Creates an asynchronous SQLAlchemy engine with the given TEST_DB_ASYNC URL.
    Initializes the schema by running `SQLModel.metadata.create_all(engine)`.
    Returns the created engine.
    """
    
    engine = create_async_engine(TEST_DB_ASYNC, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


# ============================================================
# 3) RESET TABLES BEFORE EACH TEST
# ============================================================
@pytest_asyncio.fixture(autouse=True)
async def reset_db(async_engine):
    """
    Resets the database by dropping all tables and recreating them.
    This is run before every test to ensure a clean slate.
    """
    
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield


# ============================================================
# 4) PATCH DB + async_session BEFORE importing app
# ============================================================
@pytest_asyncio.fixture
async def patched_app(async_engine, monkeypatch):
    """
    Patches the FastAPI app with the given async_engine and monkeypatch.
    Reloading the Settings and FastAPI app with the correct env vars.
    Patches the DB with the given async_engine.
    Returns the freshly reloaded app with the correct settings.
    """
    
    from importlib import reload

    import app.core.config as config
    import app.main as main

    reload(config)   # reload Settings()
    reload(main)     # reload FastAPI app (routers, dependencies)

    # Patch DB
    from sqlmodel.ext.asyncio.session import \
        AsyncSession as SQLModelAsyncSession
    async_sessionmaker = sessionmaker(
        async_engine,
        class_=SQLModelAsyncSession,
        expire_on_commit=False
    )

    monkeypatch.setattr("app.db.engine", async_engine)
    monkeypatch.setattr("app.db.async_session", lambda: async_sessionmaker())

    # Return freshly reloaded app with the correct settings
    return main.app


# ============================================================
# 5) SEED ADMIN — this time settings match correctly
# ============================================================
@pytest_asyncio.fixture(autouse=True)
async def seed_default_admin(async_engine):
    """
    Seeds the default admin with username "admin" and password "admin".
    Resets the admins table before seeding the default admin.
    """
    
    from sqlmodel.ext.asyncio.session import \
        AsyncSession as SQLModelAsyncSession

    from app.auth import hash_password
    from app.models import Admin

    async_sessionmaker = sessionmaker(
        async_engine,
        class_=SQLModelAsyncSession,
        expire_on_commit=False
    )

    async with async_sessionmaker() as session:
        await session.execute(text("DELETE FROM admins"))
        session.add(Admin(
            username="admin",
            hashed_password=hash_password("admin")
        ))
        await session.commit()


# ============================================================
# 6) SQLite compatibility patch (exists/array_agg/timestamps)
# ============================================================
@pytest.fixture(autouse=True)
def patch_exec(monkeypatch):
    """
    Patches the AsyncSession.exec method to handle SQLite compatibility issues.

    - "exists" is patched to return False, None, and [] for first, one_or_none, and all respectively.
    - "array_agg" and "array_remove" are patched to return ([],) for first, one_or_none, and [(,)] for all respectively.
    - Datetimes returned by the exec method are patched to have timezone.utc if they don't already have a timezone.

    This fixture should be used in tests that use an SQLite database.
    """
    
    from sqlmodel.ext.asyncio.session import AsyncSession

    original_exec = AsyncSession.exec

    async def fixed_exec(self, statement, *args, **kwargs):
        sql = str(statement).lower()

        if "exists" in sql:
            m = MagicMock()
            m.first.return_value = False
            m.one_or_none.return_value = None
            m.all.return_value = []
            return m

        if "array_agg" in sql or "array_remove" in sql:
            m = MagicMock()
            m.first.return_value = ([],)
            m.one_or_none.return_value = ([],)
            m.all.return_value = [([],)]
            return m

        result = await original_exec(self, statement, *args, **kwargs)

        def norm(row):
            if row is None:
                return None
            if isinstance(row, list) and len(row) == 1:
                row = row[0]
            if hasattr(row, "__dict__"):
                for k, v in row.__dict__.items():
                    if isinstance(v, datetime) and v.tzinfo is None:
                        setattr(row, k, v.replace(tzinfo=timezone.utc))
                return row
            if not isinstance(row, tuple):
                return row
            fixed = []
            for v in row:
                if isinstance(v, datetime) and v.tzinfo is None:
                    fixed.append(v.replace(tzinfo=timezone.utc))
                else:
                    fixed.append(v)
            return tuple(fixed)

        if hasattr(result, "first"):
            orig = result.first
            result.first = lambda: norm(orig())
        if hasattr(result, "one_or_none"):
            orig = result.one_or_none
            result.one_or_none = lambda: norm(orig())
        if hasattr(result, "all"):
            orig = result.all
            result.all = lambda: [norm(r) for r in orig()]

        return result

    monkeypatch.setattr(AsyncSession, "exec", fixed_exec)
    yield


# ============================================================
# 7) TEST CLIENT WITH REDIS MOCK
# ============================================================
@pytest.fixture
def client(patched_app):
    """
    A fixture that returns a TestClient with a patched Redis client.

    The Redis client is patched to return None for get and True for set.
    This allows tests to run without a Redis server.
    """
    
    with patch("app.routers.user.redis.from_url") as m1, \
         patch("app.routers.admin.redis.from_url") as m2:

        r = AsyncMock()
        r.get.return_value = None
        r.set.return_value = True

        m1.return_value = r
        m2.return_value = r

        yield TestClient(patched_app)
