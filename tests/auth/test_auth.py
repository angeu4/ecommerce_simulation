from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import (create_jwt, decode_jwt, get_current_admin,
                      get_current_user, hash_password, verify_password)
from app.core.constants import TokenStatus
from app.core.exceptions import AuthError
from app.models import Admin, EndUser, Token


# -----------------------------
# JWT CREATION + DECODING
# -----------------------------
def test_create_and_decode_jwt_user():
    """
    Tests that a JWT token can be created and decoded correctly for a user.
    """
    
    urn = "urn:user:123"
    token = create_jwt(urn, is_admin=False, expires_seconds=3600)

    decoded = decode_jwt(token, is_admin=False)
    assert decoded["sub"] == urn
    assert decoded["admin"] is False


def test_create_and_decode_jwt_admin():
    """
    Tests that a JWT token can be created and decoded correctly for an admin.
    It tests that the token contains the correct urn and admin status.
    """
    
    urn = "urn:admin:999"
    token = create_jwt(urn, is_admin=True)

    decoded = decode_jwt(token, is_admin=True)
    assert decoded["sub"] == urn
    assert decoded["admin"] is True


def test_decode_jwt_invalid():
    """
    Tests that decode_jwt raises an AuthError when given an invalid token.
    """
    
    with pytest.raises(AuthError):
        decode_jwt("BAD.TOKEN.123", is_admin=False)


# -----------------------------
# PASSWORD HASHING
# -----------------------------
def test_password_hash_and_verify():
    """
    Tests that the password hashing and verification functions work correctly.
    It tests that a correctly hashed password can be verified correctly, and that
    an incorrect password cannot be verified.
    """

    hashed = hash_password("secret")
    assert verify_password("secret", hashed) is True
    assert verify_password("wrong", hashed) is False


# -----------------------------
# Dummy helpers
# -----------------------------
class DummyRequest:
    def __init__(self):
        self.state = MagicMock()
        self.state.request_id = "REQ-TEST"


def make_creds(token="TOKEN"):
    """
    Creates an HTTPAuthorizationCredentials object with the given token.

    :param token: The token to use in the credentials, defaults to "TOKEN"
    :return: An HTTPAuthorizationCredentials object with the given token
    """
    
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


# -----------------------------
# Helper for all DB mocks
# -----------------------------
def build_exec_mock(token_row=None, user=None, admin=None):
    """
    Returns an async mock_exec(query) that detects which model
    is being selected by reading query.column_descriptions[0]["entity"].
    """

    async def mock_exec(query):
        # SQLModel always fills this with the selected model class
        model = query.column_descriptions[0].get("entity")

        if model is Token:
            return MagicMock(one_or_none=lambda: token_row)

        if model is EndUser:
            return MagicMock(one_or_none=lambda: user)

        if model is Admin:
            return MagicMock(one_or_none=lambda: admin)

        return MagicMock(one_or_none=lambda: None)

    return mock_exec


# -----------------------------
# get_current_user — SUCCESS
# -----------------------------
@pytest.mark.asyncio
async def test_get_current_user_success():
    """
    Tests that get_current_user returns the correct user
    when given a valid JWT token that corresponds to an existing user.
    """
    
    user = EndUser(urn="urn:user:1", username="a")
    token_str = "VALID_TOKEN"

    token_row = Token(
        token=token_str,
        urn="urn:user:1",
        status=TokenStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    with patch("app.auth.decode_jwt", return_value={"sub": "urn:user:1", "jti": "x"}), \
         patch("app.auth.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        # Inject correct query detection
        mock_sess.exec = build_exec_mock(
            token_row=token_row,
            user=user
        )

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        req = DummyRequest()
        result = await get_current_user(req, creds=make_creds(token_str))

        assert result == user


# -----------------------------
# get_current_user — MISSING CREDS
# -----------------------------
@pytest.mark.asyncio
async def test_get_current_user_missing_creds():
    """
    Tests that get_current_user raises an AuthError when given None as the credentials.
    """
    
    req = DummyRequest()

    with pytest.raises(AuthError):
        await get_current_user(req, creds=None)


# -----------------------------
# get_current_user — INVALID TOKEN
# -----------------------------
@pytest.mark.asyncio
async def test_get_current_user_invalid_token():
    """
    Tests that get_current_user raises an AuthError when given an invalid token.
    The token is invalid if it cannot be decoded or if the decoded token does not match any user in the database.
    """
    
    req = DummyRequest()

    with patch("app.auth.decode_jwt", side_effect=AuthError("bad")):
        with pytest.raises(AuthError):
            await get_current_user(req, creds=make_creds("BAD"))


# -----------------------------
# get_current_user — TOKEN NOT FOUND IN DB
# -----------------------------
@pytest.mark.asyncio
async def test_get_current_user_token_not_in_db():
    """
    Tests that get_current_user raises an AuthError when given a valid token but the token is not found in the database.
    """
    
    req = DummyRequest()

    with patch("app.auth.decode_jwt", return_value={"sub": "urn:user:1", "jti": "x"}), \
         patch("app.auth.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        mock_sess.exec = build_exec_mock(
            token_row=None,  # token lookup fails
            user=None
        )

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        with pytest.raises(AuthError):
            await get_current_user(req, creds=make_creds("T"))


# -----------------------------
# get_current_user — TOKEN REVOKED
# -----------------------------
@pytest.mark.asyncio
async def test_get_current_user_token_revoked():
    """
    Tests that get_current_user raises an AuthError when given a valid token that has been revoked.
    """
    
    req = DummyRequest()

    token_row = Token(
        token="X",
        urn="urn:user:1",
        status=TokenStatus.REVOKED
    )

    with patch("app.auth.decode_jwt", return_value={"sub": "urn:user:1", "jti": "x"}), \
         patch("app.auth.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        mock_sess.exec = build_exec_mock(
            token_row=token_row,
            user=None
        )

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        with pytest.raises(AuthError):
            await get_current_user(req, creds=make_creds("X"))


# -----------------------------
# get_current_user — USER NOT FOUND
# -----------------------------
@pytest.mark.asyncio
async def test_get_current_user_user_not_found():
    """
    Tests that get_current_user raises an AuthError when given a valid token that corresponds to a user that is not found in the database.
    """
    
    req = DummyRequest()

    token_row = Token(
        token="X",
        urn="urn:user:1",
        status=TokenStatus.ACTIVE
    )

    with patch("app.auth.decode_jwt", return_value={"sub": "urn:user:1", "jti": "x"}), \
         patch("app.auth.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        mock_sess.exec = build_exec_mock(
            token_row=token_row,
            user=None
        )

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        with pytest.raises(AuthError):
            await get_current_user(req, creds=make_creds("X"))


# -----------------------------
# get_current_admin — API KEY BYPASS
# -----------------------------
@pytest.mark.asyncio
async def test_get_current_admin_api_key_success():
    """
    Tests that get_current_admin returns the correct admin object when given a valid API key.

    GIVEN a valid API key
    WHEN a request is sent to get_current_admin with the correct API key
    THEN the response should contain the correct admin object
    AND the response should have the "api_key" attribute set to True
    """
    
    req = DummyRequest()

    result = await get_current_admin(
        req,
        creds=None,
        x_api_key="XXXXX"  # MUST match .env.test
    )

    assert result["api_key"] is True


# -----------------------------
# get_current_admin — MISSING CREDS
# -----------------------------
@pytest.mark.asyncio
async def test_get_current_admin_missing_creds():
    """
    Tests that get_current_admin raises an AuthError when given None as the credentials.
    """
    
    req = DummyRequest()

    with pytest.raises(AuthError):
        await get_current_admin(req, creds=None, x_api_key=None)


# -----------------------------
# get_current_admin — SUCCESS CASE
# -----------------------------
@pytest.mark.asyncio
async def test_get_current_admin_success():
    """
    Tests that get_current_admin returns the correct admin object when given a valid JWT token.

    GIVEN a valid JWT token
    WHEN a request is sent to get_current_admin with the correct JWT token
    THEN the response should contain the correct admin object
    """
    
    req = DummyRequest()

    admin = Admin(urn="urn:admin:1", username="root")
    token_row = Token(
        token="ADMINTOKEN",
        urn="urn:admin:1",
        status=TokenStatus.ACTIVE,
        expires_at=None,
    )

    with patch("app.auth.decode_jwt", return_value={"sub": "urn:admin:1", "jti": "123"}), \
         patch("app.auth.async_session") as mock_session:

        mock_ctx = MagicMock()
        mock_sess = MagicMock()

        mock_sess.exec = build_exec_mock(
            token_row=token_row,
            admin=admin
        )

        mock_ctx.__aenter__.return_value = mock_sess
        mock_session.return_value = mock_ctx

        result = await get_current_admin(
            req,
            creds=make_creds("ADMINTOKEN"),
            x_api_key=None
        )

        assert result == admin
