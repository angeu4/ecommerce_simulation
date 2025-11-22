from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.constants import DEFAULT_DISCOUNT_PERCENTAGE


# Common base response model for consistent request_id
class ResponseBase(BaseModel):
    request_id: str = Field(default="")


# ============== ADMIN RELATED SCHEMAS ==============

class AdminCreateRequest(BaseModel):
    username: str
    password: str


class AdminCreateResponse(BaseModel):
    urn: str
    request_id: str


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    request_id: str


class AdminLogoutResponse(BaseModel):
    message: str
    request_id: str


class DiscountCodesResponse(BaseModel):
    code: str
    request_id: str


class OrderSummary(BaseModel):
    order_urn: str
    subtotal: float
    discount: float
    total: float
    applied_discount_code: Optional[str]
    items_fulfilled: int


class SummaryResponse(BaseModel):
    users_served: int
    items_fulfilled: int
    total_purchase_amount: float
    utilized_discount_codes: List[str]
    total_discount_amount: float
    orders_completed: int
    orders: List[OrderSummary]
    request_id: str


class DiscountNUpdateRequest(BaseModel):
    n: int
    discount_percentage: Optional[int] = DEFAULT_DISCOUNT_PERCENTAGE


class DiscountNUpdateResponse(BaseModel):
    message: str
    request_id: str


# ============== USER RELATED SCHEMAS ==============

class UserCreateRequest(BaseModel):
    username: str
    password: str


class UserCreateResponse(BaseModel):
    urn: str
    request_id: str


class UserLoginRequest(BaseModel):
    username: str
    password: str


class UserLoginResponse(BaseModel):
    access_token: str
    request_id: str


class UserLogoutResponse(BaseModel):
    message: str
    request_id: str


class CartItem(BaseModel):
    sku: str
    name: str
    qty: int
    price: Decimal


class CartItemsAddRequest(BaseModel):
    items: List[CartItem]


class CartItemsAddResponse(BaseModel):
    total_items_added: int
    request_id: str


class CheckoutRequest(BaseModel):
    discount_code: Optional[str] = None


class CheckoutResponse(BaseModel):
    order_urn: str
    subtotal: float
    discount: float
    total: float
    applied_discount_code: Optional[str]
    is_order_globally_nth: bool
    request_id: str


# ============== MISC SCHEMAS ==============

class ErrorResponse(BaseModel):
    error: str
    request_id: str


class HealthResponse(BaseModel):
    status: str
    request_id: str
