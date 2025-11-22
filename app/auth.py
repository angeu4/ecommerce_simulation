import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import select

from app.core.config import settings
from app.core.constants import REQUEST_ID_SYSTEM, TokenStatus
from app.core.exceptions import AuthError
from app.core.logging_setup import get_logger
from app.db import async_session
from app.models import Admin, EndUser, Token

logger = get_logger(__name__)

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


def create_jwt(urn: str, is_admin: bool, expires_seconds: int = 3600) -> str:
    """
    Creates a JWT token for the given user.

    Parameters:
    - urn: User URN
    - is_admin: Whether the user is an admin or not
    - expires_seconds: Token expiration in seconds (default: 3600)

    Returns:
    - str: JWT token
    """
    
    secret = settings.ADMIN_JWT_SECRET if is_admin else settings.USER_JWT_SECRET
    now = datetime.now(timezone.utc)

    payload = {
        "sub": urn,
        "admin": is_admin,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_seconds)).timestamp()),
        "jti": str(uuid.uuid4())
    }

    token = jwt.encode(payload, secret, algorithm="HS256")

    logger.info(
        f"Created JWT for {urn}",
        extra={"request_id": REQUEST_ID_SYSTEM, "is_admin": is_admin}
    )

    return token


def decode_jwt(token: str, is_admin: bool):
    """
    Decodes a JWT token.

    Parameters:
    - token: JWT token to decode
    - is_admin: Whether the user is an admin or not

    Returns:
    - dict: Decoded JWT payload

    Raises:
    - AuthError: If the token is invalid
    """
    
    secret = settings.ADMIN_JWT_SECRET if is_admin else settings.USER_JWT_SECRET
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError as _:
        raise AuthError("Invalid token")


def hash_password(password: str) -> str:
    """
    Hashes a given password using the argon2 password hashing algorithm.

    Parameters:
    - password: The password to hash

    Returns:
    - str: The hashed password
    """
    
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """
    Verifies a given password against a hashed password using the argon2 password hashing algorithm.

    Parameters:
    - password: The password to verify
    - hashed: The hashed password to compare against

    Returns:
    - bool: Whether the password is valid or not
    """
    
    return pwd_context.verify(password, hashed)


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer)
) -> EndUser:
    """
    Retrieves the currently authenticated user from the request.

    Parameters:
    - request: The incoming request object
    - creds: The HTTP authorization credentials (i.e. the JWT token)

    Returns:
    - EndUser: The currently authenticated end user

    Raises:
    - AuthError: If the JWT token is invalid, expired, or missing
    - AuthError: If the user associated with the JWT token is not found
    """
    
    request_id = request.state.request_id

    # checking if JWT token exists
    if not creds or not creds.credentials:
        logger.warning(
            "User authentication failed: missing credentials",
            extra={"request_id": request_id}
        )
        raise AuthError("Missing credentials")

    token_str = creds.credentials

    # decoding JWT
    try:
        payload = decode_jwt(token_str, is_admin=False)
    except Exception as e:
        logger.warning(
            f"User token decode failed: {str(e)}",
            extra={"request_id": request_id}
        )
        raise AuthError("Invalid or expired token")

    urn = payload.get("sub")
    jti = payload.get("jti")

    if not urn or not jti:
        logger.warning(
            "Malformed user JWT payload",
            extra={"request_id": request_id}
        )
        raise AuthError("Invalid token payload")

    logger.info(
        f"Verifying user with URN {urn}",
        extra={"request_id": request_id}
    )

    # validating the token record in the DB
    async with async_session() as session:
        result_token = await session.exec(
            select(Token).where(Token.token == token_str)
        )
        db_token = result_token.one_or_none()

        if not db_token:
            logger.warning(
                "Token not found in database",
                extra={"request_id": request_id, "urn": urn}
            )
            raise AuthError("Token revoked or invalid")

        # Token must be active
        if db_token.status != TokenStatus.ACTIVE:
            logger.warning(
                f"User token is not active (status={db_token.status})",
                extra={"request_id": request_id, "urn": urn}
            )
            raise AuthError("Token revoked or expired")

        # DB-level expiration check (optional but recommended)
        if db_token.expires_at and db_token.expires_at < datetime.now(timezone.utc):
            logger.warning(
                "User token expired according to DB timestamp",
                extra={"request_id": request_id, "urn": urn}
            )
            db_token.status = "expired"
            await session.commit()
            raise AuthError("Token expired")

        # extracting EndUser
        result_user = await session.exec(
            select(EndUser).where(EndUser.urn == urn)
        )
        user = result_user.one_or_none()

    if not user:
        logger.warning(
            f"User with URN {urn} not found",
            extra={"request_id": request_id}
        )
        raise AuthError("User not found")

    # returning the EndUser via happy path
    logger.info(
        f"User authentication successful for {urn}",
        extra={"request_id": request_id}
    )

    return user


async def get_current_admin(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    x_api_key: str | None = Header(default=None)
) -> Admin:
    """
    Retrieve the currently authenticated admin.

    Parameters:
    - request: Request object containing request_id
    - creds: HTTPAuthorizationCredentials containing the JWT token
    - x_api_key: str | None = Header containing the API key to bypass token validation

    Returns:
    - Admin object containing the currently authenticated admin

    Raises:
    - AuthError with status code 401 and error "Missing credentials" if JWT token is missing
    - AuthError with status code 401 and error "Invalid or expired token" if JWT token is invalid or expired
    - AuthError with status code 401 and error "Admin not found" if admin with given URN is not found
    """

    request_id = request.state.request_id

    # API Key supersedes token validation
    if x_api_key and x_api_key == settings.ADMIN_API_KEY:
        logger.info(
            "Admin authenticated via API key",
            extra={"request_id": request_id}
        )
        return {"urn": "urn:admin:api-key", "api_key": True}

    # checking if JWT token exists
    if not creds or not creds.credentials:
        logger.warning(
            "Admin authentication failed: missing credentials",
            extra={"request_id": request_id}
        )
        raise AuthError("Missing credentials")

    token_str = creds.credentials

    # decoding JWT
    try:
        payload = decode_jwt(token_str, is_admin=True)
    except Exception as e:
        logger.warning(
            f"Admin token decode failed: {str(e)}",
            extra={"request_id": request_id}
        )
        raise AuthError("Invalid or expired token")

    urn = payload.get("sub")
    jti = payload.get("jti")

    if not urn or not jti:
        logger.warning(
            "Malformed admin JWT",
            extra={"request_id": request_id}
        )
        raise AuthError("Invalid token payload")

    logger.info(
        f"Verifying admin with URN {urn}",
        extra={"request_id": request_id}
    )

    # checking token in DB
    async with async_session() as session:
        result_token = await session.exec(
            select(Token).where(Token.token == token_str)
        )
        db_token = result_token.one_or_none()

        if not db_token:
            logger.warning(
                "Token not found in database",
                extra={"request_id": request_id, "urn": urn}
            )
            raise AuthError("Token revoked or invalid")

        # Token must be active
        if db_token.status != TokenStatus.ACTIVE:
            logger.warning(
                f"Token is not active (status={db_token.status})",
                extra={"request_id": request_id, "urn": urn}
            )
            raise AuthError("Token revoked or expired")

        # If expires_at exists in DB, enforce DB-level expiration
        if db_token.expires_at and db_token.expires_at < datetime.now(timezone.utc):
            logger.warning(
                "Token expired according to DB timestamp",
                extra={"request_id": request_id, "urn": urn}
            )
            db_token.status = "expired"
            await session.commit()
            raise AuthError("Token expired")

        # validating if Admin exists
        result_admin = await session.exec(
            select(Admin).where(Admin.urn == urn)
        )
        admin = result_admin.one_or_none()

    if not admin:
        logger.warning(
            f"Admin with URN {urn} not found",
            extra={"request_id": request_id}
        )
        raise AuthError("Admin not found")

    # returning the Admin via happy path
    logger.info(
        f"Admin authentication successful for {urn}",
        extra={"request_id": request_id}
    )
    return admin

