import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.middleware.api_logger import ApiLoggerMiddleware, mask_sensitive
from app.models import ApiLog


def test_mask_sensitive_dict():
    """
    Tests that the mask_sensitive function correctly masks sensitive
    information in a dictionary.

    Given a dictionary with a password key, the function should return
    a new dictionary with the password replaced with "xxxxxx".
    """
    
    data = {"username": "john", "password": "secret"}
    masked = mask_sensitive(data)
    assert masked["password"] == "xxxxxx"
    assert masked["username"] == "john"


def test_mask_sensitive_nested():
    """
    Tests that the mask_sensitive function correctly masks sensitive
    information in a nested dictionary.

    Given a nested dictionary with a password key, the function should
    return a new nested dictionary with the password replaced with
    "xxxxxx".
    """
    
    data = {
        "level1": {
            "pwd": "abc",
            "inner": {"pass": "xyz"}
        }
    }
    masked = mask_sensitive(data)
    assert masked["level1"]["pwd"] == "xxxxxx"
    assert masked["level1"]["inner"]["pass"] == "xxxxxx"


def test_mask_sensitive_list():
    """
    Tests that the mask_sensitive function correctly masks sensitive
    information in a list of dictionaries.

    Given a list of dictionaries with a password key, the function should
    return a new list of dictionaries with the password replaced with
    "xxxxxx".
    """

    data = [{"password": "123"}]
    masked = mask_sensitive(data)
    assert masked[0]["password"] == "xxxxxx"


@pytest.fixture
def test_app():
    """
    Build a small FastAPI app with ApiLoggerMiddleware attached.
    """
    app = FastAPI()

    app.add_middleware(ApiLoggerMiddleware)

    @app.post("/login")
    async def login(payload: dict):
        return JSONResponse({"status": "ok"})

    return app


def test_middleware_logs_and_stores_entry(test_app):
    """
    Verify that:
    - request passes through successfully
    - sensitive fields are masked
    - ApiLog entry is written to DB
    """
    from app.core.constants import REQUEST_ID_NO_REQUEST_ID
    from app.db import async_session

    client = TestClient(test_app)

    body = {"username": "a", "password": "secret"}

    # Perform the request
    r = client.post("/login", json=body)
    assert r.status_code == 200

    # Query log entry from DB
    async def fetch():
        async with async_session() as session:
            result = await session.execute(
                ApiLog.__table__.select().order_by(ApiLog.id.desc()).limit(1)
            )
            return result.fetchone()

    # log_entry = pytest.run(async_fn=fetch)  # helper to run async inside sync test
    log_entry = pytest.run_async(fetch)
    assert log_entry is not None

    row = log_entry._mapping
    assert row["endpoint"] == "/login"
    assert row["http_status_code"] == 200
    assert row["request_id"] == REQUEST_ID_NO_REQUEST_ID

    # Sensitive field must be masked
    payload_json = json.loads(row["request_payload"])
    assert payload_json["password"] == "xxxxxx"


def test_middleware_db_failure_logs_error(test_app, caplog):
    """
    Patches DB commit to force failure and verifies that error log is emitted.
    """
    client = TestClient(test_app)

    with patch("app.middleware.api_logger.async_session") as mock_session:
        # Create mock session context
        mock_ctx = MagicMock()

        # __aenter__ returns the session object
        mock_session_obj = MagicMock()

        # commit must be async (awaitable)
        async def mock_commit():
            raise Exception("DB FAIL")

        mock_session_obj.commit = mock_commit
        mock_session_obj.add = MagicMock()      # add() is sync in SQLAlchemy async session

        mock_ctx.__aenter__.return_value = mock_session_obj
        mock_ctx.__aexit__.return_value = False

        mock_session.return_value = mock_ctx

        # Call the endpoint
        r = client.post("/login", json={"password": "secret"})
        assert r.status_code == 200

    # Verify error was logged
    errors = [rec for rec in caplog.records if rec.levelname == "ERROR"]
    assert any("Failed to store API log" in e.message for e in errors)
