from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth import get_current_admin
from app.models import Admin
from app.routers.admin import router as admin_router


class FakeRequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        """
        A middleware that sets the request_id attribute of the request
        to a predefined value (test-request-id) and then calls the next
        middleware in the call stack.

        :param request: The incoming request
        :param call_next: The next middleware in the call stack
        :return: The response from the next middleware
        """
        
        request.state.request_id = "test-request-id"
        return await call_next(request)


def build_test_app():
    """
    Builds a test FastAPI application with a fake request-id middleware
    and overrides the get_current_admin dependency with a dummy admin.
    This allows tests to bypass authentication and focus on the business logic.
    """

    app = FastAPI()

    # fake request-id middleware for tests
    class FakeRequestIDMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.request_id = "test-request-id"
            return await call_next(request)

    app.add_middleware(FakeRequestIDMiddleware)

    # include router
    app.include_router(admin_router)

    # dependency override for ALL tests
    async def fake_admin():
        return DummyAdmin()

    app.dependency_overrides[get_current_admin] = fake_admin

    return app


class DummyAdmin:
    def __init__(self):
        self.urn = "urn:admin:test"
        self.username = "admin"


# ---------------------------------------------------------------------------
# Test: Create Admin - Success
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_admin_success():
    """
    Tests the creation of an admin user with a unique username.

    GIVEN a unique username
    WHEN a POST request is sent to /admins with a valid payload
    THEN the response should contain the URN of the newly created admin
    AND the response status code should be 201
    """

    app = build_test_app()
    client = TestClient(app)

    payload = {"username": "newadmin", "password": "pw"}

    with patch("app.routers.admin.get_current_admin", return_value=DummyAdmin()), \
         patch("app.routers.admin.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        # Username does NOT exist
        async def mock_exec(query):
            return MagicMock(first=lambda: False)

        mock_sess.exec = mock_exec
        mock_sess.add = MagicMock()
        mock_sess.commit = AsyncMock()
        mock_sess.refresh = AsyncMock()

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.post("/admins", json=payload)

        assert r.status_code == 201
        assert "urn:" in r.json()["urn"]


# ---------------------------------------------------------------------------
# Test: Create Admin - Username Taken
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_admin_username_taken():
    """
    Tests the creation of an admin user with a username that already exists.

    GIVEN a username that is already taken
    WHEN a POST request is sent to /admins with a valid payload
    THEN the response should contain an error message indicating that the username is already taken
    AND the response status code should be 409
    """

    app = build_test_app()
    client = TestClient(app)

    payload = {"username": "taken", "password": "pw"}

    with patch("app.routers.admin.get_current_admin", return_value=DummyAdmin()), \
         patch("app.routers.admin.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        async def mock_exec(query):
            return MagicMock(first=lambda: True)

        mock_sess.exec = mock_exec
        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.post("/admins", json=payload)

        assert r.status_code == 409
        assert r.json()["error"] == "Username already taken"


# ---------------------------------------------------------------------------
# Test: Admin Login Success
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_login_admin_success():
    """
    Tests the login of an admin user with valid credentials.

    GIVEN a valid admin username and password
    WHEN a POST request is sent to /auth/admin/login with the correct credentials
    THEN the response should contain a valid access token
    AND the response status code should be 200
    """
    
    app = build_test_app()
    client = TestClient(app)

    admin = Admin(username="root", hashed_password="$argon2id$hash")

    with patch("app.routers.admin.verify_password", return_value=True), \
         patch("app.routers.admin.create_jwt", return_value="TOKEN123"), \
         patch("app.routers.admin.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        async def mock_exec(query):
            return MagicMock(one_or_none=lambda: admin)

        mock_sess.exec = mock_exec
        mock_sess.add = MagicMock()
        mock_sess.commit = AsyncMock()

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.post("/auth/admin/login", json={"username": "root", "password": "x"})

        assert r.status_code == 200
        assert r.json()["access_token"] == "TOKEN123"


# ---------------------------------------------------------------------------
# Test: Admin Login Invalid Credentials
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_login_admin_invalid_credentials():
    """
    Tests the login of an admin user with invalid credentials.

    GIVEN invalid admin credentials
    WHEN a POST request is sent to /auth/admin/login with the invalid credentials
    THEN the response should contain an error message indicating that the credentials are invalid
    AND the response status code should be 401
    """
    app = build_test_app()
    client = TestClient(app)

    with patch("app.routers.admin.verify_password", return_value=False), \
         patch("app.routers.admin.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()
        mock_sess.exec = AsyncMock(return_value=MagicMock(one_or_none=lambda: None))

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.post("/auth/admin/login", json={"username": "a", "password": "b"})

        assert r.status_code == 401
        assert r.json()["error"] == "Invalid credentials"


# ---------------------------------------------------------------------------
# Test: Logout Admin - Token Not Found
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_logout_admin_token_not_found():
    """
    Tests the logout of an admin user with a token that is not found in the database.

    GIVEN a token that is not found in the database
    WHEN a POST request is sent to /auth/admin/logout with the token
    THEN the response should contain an error message indicating that the token was not found or already logged out
    AND the response status code should be 401
    """
    
    app = build_test_app()
    client = TestClient(app)

    with patch("app.routers.admin.get_current_admin", return_value=DummyAdmin()), \
         patch("app.routers.admin.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        async def mock_exec(query):
            return MagicMock(one_or_none=lambda: None)

        mock_sess.exec = mock_exec
        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.post("/auth/admin/logout", headers={"Authorization": "Bearer X"})

        assert r.status_code == 401
        assert r.json()["error"] == "Token not found or already logged out"


# ---------------------------------------------------------------------------
# Test: Discount Code Creation Success
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_discount_code_success():
    """
    Tests the creation of a discount code by an admin user.

    GIVEN a valid admin username and password
    WHEN a POST request is sent to /admin/discount-codes
    THEN the response should contain a newly generated discount code
    AND the response status code should be 201
    """
    
    app = build_test_app()
    client = TestClient(app)

    with patch("app.routers.admin.get_current_admin", return_value=DummyAdmin()), \
         patch("app.routers.admin.async_session") as mock_session, \
         patch("app.routers.admin.redis.from_url") as mock_redis:

        redis_mock = AsyncMock()
        mock_redis.return_value = redis_mock

        mock_ctx = MagicMock()
        mock_sess = MagicMock()
        mock_sess.add = MagicMock()
        mock_sess.commit = AsyncMock()

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.post("/admin/discount-codes")

        assert r.status_code == 201
        assert len(r.json()["code"]) == 8


# ---------------------------------------------------------------------------
# Test: Admin Summary
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_admin_summary_success():
    """
    Tests the retrieval of the admin summary report.

    GIVEN a valid admin username and password
    WHEN a GET request is sent to /admin/reports/summary
    THEN the response should contain the global summary and order summary
    AND the response status code should be 200
    """
    
    app = build_test_app()
    client = TestClient(app)

    admin = DummyAdmin()

    with patch("app.routers.admin.get_current_admin", return_value=admin), \
         patch("app.routers.admin.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        # Fake global summary row
        class FakeGlobal:
            users_served = 10
            orders_completed = 3
            total_purchase_amount = 100
            total_discount_amount = 20
            items_fulfilled = 5
            utilized_discount_codes = ["ABC", "XYZ"]

        # Fake order summary row
        fake_order_row = ("urn:o1", 50, 40, "ABC", 2)

        async def mock_exec(query):
            return MagicMock(
                one=lambda: FakeGlobal(),
                all=lambda: [fake_order_row]
            )

        mock_sess.exec = mock_exec
        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.get("/admin/reports/summary")

        assert r.status_code == 200
        assert r.json()["users_served"] == 10
        assert len(r.json()["orders"]) == 1


# ---------------------------------------------------------------------------
# Test: Update Discount N Config Success
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_discount_n_success():
    """
    Tests the update of the discount N config by an admin user.

    GIVEN a valid admin username and password
    WHEN a PUT request is sent to /admin/config/discount-n with a valid payload
    THEN the response should contain a success message indicating that the discount N config was updated successfully
    AND the response status code should be 200
    """
    
    app = build_test_app()
    client = TestClient(app)

    with patch("app.routers.admin.get_current_admin", return_value=DummyAdmin()), \
         patch("app.routers.admin.redis.from_url") as mock_redis:

        redis_mock = AsyncMock()
        mock_redis.return_value = redis_mock

        r = client.put(
            "/admin/config/discount-n",
            json={"n": 3, "discount_percentage": 15}
        )

        assert r.status_code == 200
        assert "15% discount applies every 3rd order" in r.json()["message"]
