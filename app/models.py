import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, DateTime, Enum
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel

from app.core.constants import ItemStatus, TokenStatus


def generate_urn(prefix: str) -> str:
    """
    Generates a URN (Uniform resource name) based on the given prefix.

    A URN is a unique identifier that is used to identify a resource.
    It is composed of three parts: a namespace identifier, a local name, and an optional NAI (name authority identifier).

    The generated URN has the format "urn:<prefix>:<uuid4>".

    Args:
        prefix (str): The prefix to be used in the URN.

    Returns:
        str: The generated URN.
    """
    
    return f"urn:{prefix}:{uuid.uuid4()}"


class EndUser(SQLModel, table=True):
    __tablename__ = "end_users"

    id: Optional[int] = Field(default=None, primary_key=True)
    urn: str = Field(default_factory=lambda: generate_urn("end_user"), index=True, unique=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class Admin(SQLModel, table=True):
    __tablename__ = "admins"

    id: Optional[int] = Field(default=None, primary_key=True)
    urn: str = Field(default_factory=lambda: generate_urn("admin"), index=True, unique=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class Item(SQLModel, table=True):
    __tablename__ = "items"

    id: Optional[int] = Field(default=None, primary_key=True)
    urn: str = Field(default_factory=lambda: generate_urn("item"), index=True, unique=True)
    owner_urn: str = Field(index=True)
    sku: str
    name: str
    qty: int
    price: Decimal
    status: ItemStatus = Field(
        sa_column=Column(
            Enum(ItemStatus, name="item_status_enum"),
            nullable=False,
            default=ItemStatus.PENDING
        )
    )
    order_urn: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    fulfilled_at: Optional[datetime] = Field(
        sa_column=Column(DateTime(timezone=True))
    )


class Order(SQLModel, table=True):
    __tablename__ = "orders"

    id: Optional[int] = Field(default=None, primary_key=True)
    urn: str = Field(default_factory=lambda: generate_urn("order"), index=True, unique=True)
    owner_urn: str = Field(index=True)
    subtotal: Decimal
    discount_code: Optional[str] = None
    total: Decimal
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class DiscountCode(SQLModel, table=True):
    __tablename__ = "discount_codes"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: Optional[str] = Field(index=True, unique=True)
    used: bool = Field(default=False)
    user_urn: Optional[str] = Field(default=None, index=True)
    order_urn: Optional[str] = Field(default=None, index=True)
    issued_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    expires_at: Optional[datetime] = Field(
        sa_column=Column(DateTime(timezone=True))
    )


class Token(SQLModel, table=True):
    __tablename__ = "tokens"

    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(unique=True, index=True)
    owner_urn: str = Field(index=True)
    status: TokenStatus = Field(
        sa_column=Column(
            Enum(TokenStatus, name="token_status_enum"),
            nullable=False,
            default=TokenStatus.ACTIVE
        )
    )
    expires_at: Optional[datetime] = Field(
        sa_column=Column(DateTime(timezone=True))
    )
    revoked_at: Optional[datetime] = Field(
        sa_column=Column(DateTime(timezone=True))
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class ApiLog(SQLModel, table=True):
    __tablename__ = "api_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    request_id: str = Field(index=True)
    endpoint: str
    request_payload: str
    http_status_code: int
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
