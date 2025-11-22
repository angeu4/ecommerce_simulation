import os
import pathlib
import pytest
from dotenv import load_dotenv
import asyncio

# -----------------------------------------------------------
# 1. Load `.env.test` BEFORE importing any app modules
# -----------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parent
load_dotenv(ROOT / ".env.test")

# Tell logging_setup to use a temp dir
os.environ["PYTEST_RUNNING"] = "1"

# -----------------------------------------------------------
# 2. Set up the SQLite database synchronously for tests
# -----------------------------------------------------------
from sqlmodel import SQLModel, create_engine # noqa
from app.db import engine  # noqa


@pytest.fixture(scope="session", autouse=True)
def initialize_test_db():
    """
    Sync fixture that drops & recreates all tables
    using a separate synchronous engine.

    This avoids all pytest async fixture warnings.
    """

    # Use the same DB URL as the async engine
    from app.core.config import settings

    sync_engine = create_engine(
        settings.DATABASE_URL.replace("+aiosqlite", ""), echo=False
    )

    SQLModel.metadata.drop_all(sync_engine)
    SQLModel.metadata.create_all(sync_engine)

    yield


@pytest.fixture
def run():
    loop = asyncio.get_event_loop()
    def _run(async_fn):
        return loop.run_until_complete(async_fn)
    return _run

# usage: pytest.run(async_fn=...)
pytest.run = lambda async_fn: asyncio.get_event_loop().run_until_complete(async_fn)


@pytest.fixture(scope="session", autouse=True)
def enable_async_run():
    pytest.run_async = lambda fn: asyncio.get_event_loop().run_until_complete(fn())
