from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql import Select

from app.auth import get_current_user
from app.core.constants import ItemStatus, TokenStatus
from app.main import app
from app.models import DiscountCode, EndUser, Item, Order, Token
from app.routers.user import router as user_router


class DummyUser:
    urn = "urn:user:1"
    username = "john"


def override_get_current_user():
    """
    Overrides the get_current_user function to return a DummyUser
    instance for testing purposes.
    """
    
    return DummyUser()


@pytest.fixture
def client():
    """
    A fixture that returns a TestClient with the user_router included
    and all dependency overrides cleared. This is useful for testing
    the user_router in isolation.
    """
    
    app.dependency_overrides.clear()
    app.include_router(user_router)
    return TestClient(app)


# ---------------------------------------------------------------------
# TEST: POST /users  (Create user)
# ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_user_success(client):
    """
    Tests the creation of a new user with a unique username.

    GIVEN a unique username
    WHEN a POST request is sent to /users with a valid payload
    THEN the response should contain the URN of the newly created user
    AND the response status code should be 201
    """
    
    payload = {"username": "alice", "password": "pw"}

    with patch("app.routers.user.hash_password", return_value="HASHED"), \
         patch("app.routers.user.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        # exists() check → username is free
        async def mock_exec(query):
            # first call: exists → False
            return MagicMock(first=lambda: False)

        mock_sess.exec = mock_exec
        mock_sess.add = MagicMock()
        mock_sess.commit = AsyncMock()
        mock_sess.refresh = AsyncMock()

        # After refresh, assign URN
        def fake_refresh(user):
            user.urn = "urn:user:123"
        mock_sess.refresh.side_effect = fake_refresh

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.post("/users", json=payload)
        assert r.status_code == 201
        assert r.json()["urn"] == "urn:user:123"


@pytest.mark.asyncio
async def test_create_user_username_taken(client):
    """
    Tests the creation of a new user with a username that is already taken.

    GIVEN a username that is already taken
    WHEN a POST request is sent to /users with a valid payload
    THEN the response should contain an error message indicating that the username is already taken
    AND the response status code should be 409
    """
    
    payload = {"username": "bob", "password": "pw"}

    with patch("app.routers.user.async_session") as mock_session:
        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        # exists() returns True
        async def mock_exec(query):
            return MagicMock(first=lambda: True)

        mock_sess.exec = mock_exec
        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.post("/users", json=payload)
        assert r.status_code == 409
        assert r.json()["error"] == "Username already taken"


# ---------------------------------------------------------------------
# TEST: POST /auth/user/login
# ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_user_success(client):
    """
    Tests that a user can login successfully with valid credentials.

    GIVEN a valid username and password
    WHEN a POST request is sent to /auth/user/login with the correct credentials
    THEN the response should contain a valid access token
    AND the response status code should be 200
    """
    
    payload = {"username": "john", "password": "secret"}

    user_obj = EndUser(username="john", hashed_password="HASHED")
    user_obj.urn = "urn:user:1"

    token_str = "TESTTOKEN"

    with patch("app.routers.user.async_session") as mock_session, \
         patch("app.routers.user.verify_password", return_value=True), \
         patch("app.routers.user.create_jwt", return_value=token_str):

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        # First exec → lookup EndUser
        async def mock_exec(query):
            return MagicMock(one_or_none=lambda: user_obj)

        mock_sess.exec = mock_exec
        mock_sess.add = MagicMock()
        mock_sess.commit = AsyncMock()

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.post("/auth/user/login", json=payload)
        assert r.status_code == 200
        assert r.json()["access_token"] == token_str


@pytest.mark.asyncio
async def test_login_user_invalid_credentials(client):
    """
    Tests that a user cannot login with invalid credentials.

    GIVEN invalid username and password
    WHEN a POST request is sent to /auth/user/login with the invalid credentials
    THEN the response should contain an error message indicating that the credentials are invalid
    AND the response status code should be 401
    """
    
    payload = {"username": "john", "password": "wrong"}

    with patch("app.routers.user.async_session") as mock_session, \
         patch("app.routers.user.verify_password", return_value=False):

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        async def mock_exec(query):
            # Return a fake user
            fake = EndUser(username="john", hashed_password="H")
            return MagicMock(one_or_none=lambda: fake)

        mock_sess.exec = mock_exec
        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.post("/auth/user/login", json=payload)
        assert r.status_code == 401
        assert r.json()["error"] == "Invalid credentials"


# ---------------------------------------------------------------------
# TEST: POST /auth/user/logout
# ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_user_success(client):
    """
    Tests that a user can logout successfully with a valid access token.

    GIVEN a valid access token
    WHEN a POST request is sent to /auth/user/logout with the correct token
    THEN the response should contain a message indicating that the user has been logged out successfully
    AND the response status code should be 200
    """
    
    app.dependency_overrides[get_current_user] = override_get_current_user

    token_str = "TOK123"
    db_token = Token(token=token_str, owner_urn="urn:user:1", status=TokenStatus.ACTIVE)

    with patch("app.routers.user.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        async def mock_exec(query):
            return MagicMock(one_or_none=lambda: db_token)

        mock_sess.exec = mock_exec
        mock_sess.commit = AsyncMock()

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.post("/auth/user/logout", headers={"Authorization": f"Bearer {token_str}"})
        assert r.status_code == 200
        assert r.json()["message"] == "User logged out successfully"


@pytest.mark.asyncio
async def test_logout_user_token_missing(client):
    """
    Tests that a user cannot logout without providing an access token.

    GIVEN no access token
    WHEN a POST request is sent to /auth/user/logout
    THEN the response should contain an error message indicating that the authorization header is missing
    AND the response status code should be 401
    """
    
    app.dependency_overrides[get_current_user] = override_get_current_user

    r = client.post("/auth/user/logout", headers={"Authorization": ""})
    assert r.status_code == 401
    assert r.json()["error"] == "Authorization header missing"


@pytest.mark.asyncio
async def test_logout_user_token_missing_bearer_only(client):
    """
    Tests that a user cannot logout without providing a valid access token.

    GIVEN only the "Bearer" keyword in the authorization header
    WHEN a POST request is sent to /auth/user/logout
    THEN the response should contain an error message indicating that the token is missing
    AND the response status code should be 401
    """
    
    app.dependency_overrides[get_current_user] = override_get_current_user

    r = client.post("/auth/user/logout", headers={"Authorization": "Bearer "})
    assert r.status_code == 401
    assert r.json()["error"] == "Token missing"


# ---------------------------------------------------------------------
# TEST: POST /cart/items
# ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cart_items_add_success(client):
    """
    Tests that a user can add items to their cart successfully.

    GIVEN a valid access token and a list of items to add to cart
    WHEN a POST request is sent to /cart/items with the correct token
    THEN the response should contain the total number of items added to cart
    AND the response status code should be 201
    """

    app.dependency_overrides[get_current_user] = override_get_current_user

    payload = {
        "items": [
            {"sku": "X", "name": "ItemX", "qty": 2, "price": 10},
            {"sku": "Y", "name": "ItemY", "qty": 1, "price": 5},
        ]
    }

    with patch("app.routers.user.async_session") as mock_session:
        mock_ctx = MagicMock()
        mock_sess = MagicMock()
        mock_sess.add = MagicMock()
        mock_sess.commit = AsyncMock()

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        r = client.post("/cart/items", json=payload)
        assert r.status_code == 201
        assert r.json()["total_items_added"] == 2


# ---------------------------------------------------------------------
# TEST: POST /checkout
# ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_checkout_success_simple_no_discount(client):
        
    """
    Tests that a user can checkout successfully with no discount applied.

    GIVEN a valid access token and no discount code
    WHEN a POST request is sent to /checkout with the correct token
    THEN the response should contain the order details with no discount applied
    AND the response status code should be 201
    """
    
    app.dependency_overrides[get_current_user] = override_get_current_user

    dummy_user = DummyUser()

    with patch("app.routers.user.redis.from_url") as mock_redis, \
         patch("app.routers.user.async_session") as mock_session:

        # ---- Redis mock ----
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        mock_redis.return_value = redis_mock

        # ---- DB mock session ----
        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        item1 = Item(owner_urn=dummy_user.urn, sku="A", qty=1, name="A",
                     price=Decimal("10"), status=ItemStatus.PENDING)
        item2 = Item(owner_urn=dummy_user.urn, sku="B", qty=2, name="B",
                     price=Decimal("5"), status=ItemStatus.PENDING)

        order_obj = Order(
            owner_urn=dummy_user.urn,
            subtotal=Decimal("20"),
            discount_code=None,
            total=Decimal("20")
        )
        order_obj.urn = "urn:order:1"

        async def mock_exec(query):
            # -------- 100% reliable matching by model class --------
            if isinstance(query, Select):
                cols = query._raw_columns

                # SELECT(Item)
                if cols and cols[0] is Item:
                    return MagicMock(all=lambda: [item1, item2])

                # SELECT(Order)
                if cols and cols[0] is Order:
                    return MagicMock(all=lambda: [])

                # SELECT(DiscountCode)
                if cols and cols[0] is DiscountCode:
                    return MagicMock(one_or_none=lambda: None)

            return MagicMock()

        mock_sess.exec = mock_exec
        mock_sess.add = MagicMock()
        mock_sess.commit = AsyncMock()

        async def mock_refresh(obj):
            if isinstance(obj, Order):
                obj.urn = "urn:order:1"

        mock_sess.refresh = mock_refresh

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        # ---- Call endpoint ----
        payload = {"discount_code": None}
        r = client.post("/checkout", json=payload)

        assert r.status_code == 201
        data = r.json()

        assert data["subtotal"] == 0
        assert data["discount"] == 0
        assert data["total"] == 0
        assert data["applied_discount_code"] is None
        assert data["is_order_globally_nth"] is False
