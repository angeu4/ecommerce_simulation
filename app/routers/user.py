from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Union

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlmodel import select

from app.auth import (create_jwt, get_current_user, hash_password,
                      verify_password)
from app.core.config import settings
from app.core.constants import (DEFAULT_DISCOUNT_PERCENTAGE, ItemStatus,
                                TokenStatus)
from app.core.logging_setup import get_logger
from app.db import async_session
from app.models import DiscountCode, EndUser, Item, Order, Token
from app.schemas import (CartItemsAddRequest, CartItemsAddResponse,
                         CheckoutRequest, CheckoutResponse, ErrorResponse,
                         UserCreateRequest, UserCreateResponse,
                         UserLoginRequest, UserLoginResponse,
                         UserLogoutResponse)

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/users",
    response_model=Union[UserCreateResponse, ErrorResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_user(payload: UserCreateRequest, request: Request):
    """
    Create a new end user.

    Parameters:
    - payload: UserCreateRequest containing username and password
    - request: Request object containing request_id

    Returns:
    - UserCreateResponse containing user_urn and request_id on success
    - ErrorResponse containing error and request_id on failure

    Raises:
    - HTTPException with status code 409 and error "Username already taken" if username is already taken
    - HTTPException with status code 500 and error "/users failed" if an exception occurs during the request
    """
    
    request_id = request.state.request_id

    try:
        logger.info(
            "User register request recieved",
            extra={"request_id": request_id}
        )

        async with async_session() as session:
            
            # checking if username already taken
            exists_query = select(
                func.exists(
                    select(EndUser.id)
                    .where(EndUser.username == payload.username)
                    .scalar_subquery()
                )
            )

            exists = (await session.exec(exists_query)).first()
            
            if exists:
                logger.warning(
                    "User registration failed — username taken",
                    extra={"request_id": request_id}
                )
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content=ErrorResponse(
                        error="Username already taken",
                        request_id=request_id
                    ).model_dump()
                )

            # creating new user
            user = EndUser(username=payload.username, hashed_password=hash_password(payload.password))
            session.add(user)
            await session.commit()
            await session.refresh(user)

        logger.info(
            "User registered successfully",
            extra={"request_id": request_id, "user_urn": user.urn}
        )

        return UserCreateResponse(
            urn=user.urn,
            request_id=request_id
        )
    
    except Exception as exception:
        logger.exception(
            "/users failed due to an exception",
            extra={"error": str(exception), "request_id": request_id}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="/users failed",
                request_id=request_id
            ).model_dump()
        )


@router.post(
    "/auth/user/login",
    response_model=Union[UserLoginResponse, ErrorResponse],
)
async def login_user(payload: UserLoginRequest, request: Request):
    """
    Login a user using username and password.

    Parameters:
    - payload: UserLoginRequest containing username and password
    - request: Request object containing request_id

    Returns:
    - UserLoginResponse containing access_token and request_id on success
    - ErrorResponse containing error and request_id on failure

    Raises:
    - HTTPException with status code 401 and error "Invalid credentials" if username or password is invalid
    - HTTPException with status code 500 and error "/auth/user/login failed" if an exception occurs during the request
    """
    
    request_id = request.state.request_id

    try:
        logger.info(
            "User login request recieved",
            extra={"request_id": request_id}
        )

        # checking if User credentials correct
        async with async_session() as session:
            result = await session.exec(select(EndUser).where(EndUser.username == payload.username))
            user = result.one_or_none()

        if not user or not verify_password(payload.password, user.hashed_password):
            logger.warning(
                "User login failed — invalid credentials",
                extra={"request_id": request_id}
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=ErrorResponse(
                    error="Invalid credentials",
                    request_id=request_id
                ).model_dump()
            )

        # creating Token and JWT
        token = create_jwt(urn=user.urn, is_admin=False, expires_seconds=3600)

        async with async_session() as session:
            db_token = Token(
                token=token,
                owner_urn=user.urn,
                status=TokenStatus.ACTIVE,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=3600),
            )
            session.add(db_token)
            await session.commit()

        logger.info(
            "User logged in successfully",
            extra={"request_id": request_id, "user_urn": user.urn}
        )

        return UserLoginResponse(
            access_token=token,
            request_id=request_id
        )
    
    except Exception as exception:
        logger.exception(
            "/auth/user/login failed due to an exception",
            extra={"error": str(exception), "request_id": request_id}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="/auth/user/login failed",
                request_id=request_id
            ).model_dump()
        )


@router.post(
    "/auth/user/logout",
    response_model=Union[UserLogoutResponse, ErrorResponse],
)
async def logout_user(
    request: Request, 
    current=Depends(get_current_user)
):
    """
    Logout an end user.

    Parameters:
    - request: Request object containing the request_id

    Returns:
    - UserLogoutResponse containing message and request_id on success
    - ErrorResponse containing error and request_id on failure

    Raises:
    - HTTPException with status code 401 and error "Authorization header missing" if Authorization header is missing
    - HTTPException with status code 401 and error "Token missing" if token is missing
    - HTTPException with status code 401 and error "Token not found or already logged out" if token is not found in DB
    - HTTPException with status code 500 and error "/auth/user/logout failed" if an exception occurs during the request
    """

    request_id = request.state.request_id

    try:
        # extracting token from Authorization header
        auth_header = request.headers.get("authorization")
        if not auth_header:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=ErrorResponse(
                    error="Authorization header missing",
                    request_id=request_id
                ).model_dump()
            )

        stringified_token = auth_header.replace("Bearer ", "").strip()
        if not stringified_token:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=ErrorResponse(
                    error="Token missing",
                    request_id=request_id
                ).model_dump()
            )

        # fetching token from DB
        async with async_session() as session:
            result = await session.exec(
                select(Token).where(Token.token == stringified_token)
            )
            db_token = result.one_or_none()

            if not db_token:
                # Token not found in DB means already invalid
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=ErrorResponse(
                        error="Token not found or already logged out",
                        request_id=request_id
                    ).model_dump()
                )

            # marking token as revoked
            db_token.status = TokenStatus.REVOKED
            db_token.revoked_at = datetime.now(timezone.utc)
            await session.commit()

        logger.info(
            "User logged out successfully",
            extra={
                "request_id": request_id,
                "admin_urn": current.urn,
                "token": stringified_token
            }
        )

        return UserLogoutResponse(
            message="User logged out successfully",
            request_id=request_id
        )

    except Exception as exception:
        logger.exception(
            "/auth/user/logout failed due to exception",
            extra={"error": str(exception), "request_id": request_id}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="/auth/user/logout failed",
                request_id=request_id
            ).model_dump()
        )


@router.post(
    "/cart/items",
    response_model=Union[CartItemsAddResponse, ErrorResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_cart_items(payload: CartItemsAddRequest, request: Request, current=Depends(get_current_user)):
    """
    Adds items to the cart for a given user.

    Args:
        payload (CartItemsAddRequest): Request body containing items to add to cart.
        request (Request): Request object containing request metadata.
        current (EndUser): Current user object returned by get_current_user dependency.

    Returns:
        Union[CartItemsAddResponse, ErrorResponse]: Either a CartItemsAddResponse containing the total number of items added to cart, or an ErrorResponse containing an error message.

    Raises:
        Exception: If an exception occurs during the execution of this method.
    """

    request_id = request.state.request_id

    try:
        logger.info(
            f"Adding {len(payload.items)} items to cart for user_urn={current.urn}",
            extra={"request_id": request_id, "user_urn": current.urn}
        )

        # looping over cart items and inserting into DB
        async with async_session() as session:
            for payload_item in payload.items:
                item = Item(
                    owner_urn=current.urn,
                    sku=payload_item.sku,
                    name=payload_item.name,
                    qty=payload_item.qty,
                    price=payload_item.price,
                    status=ItemStatus.PENDING
                )
                session.add(item)
            await session.commit()

        logger.info(
            "Items added to cart successfully",
            extra={"request_id": request_id, "count": len(payload.items), "user_urn": current.urn}
        )

        return CartItemsAddResponse(
            total_items_added=len(payload.items),
            request_id=request_id
        )
    
    except Exception as exception:
        logger.exception(
            "/cart/items failed due to an exception",
            extra={"error": str(exception), "request_id": request_id}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="/cart/items failed",
                request_id=request_id
            ).model_dump()
        )


@router.post(
    "/checkout",
    response_model=Union[CheckoutResponse, ErrorResponse],
    status_code=status.HTTP_201_CREATED,
)
async def perform_checkout(payload: CheckoutRequest, request: Request, current=Depends(get_current_user)):
    """
    Performs checkout for an end user.

    Parameters:
    - payload: CheckoutRequest containing the requested discount code
    - request: Request object containing the request_id
    - current: EndUser object containing the end user's details

    Returns:
    - CheckoutResponse containing the order_urn, subtotal, discount, total, applied_discount_code, is_order_globally_nth, and request_id on success
    - ErrorResponse containing error and request_id on failure

    Raises:
    - HTTPException with status code 500 and error "/checkout failed" if an exception occurs during the request
    """

    request_id = request.state.request_id

    try:
        logger.info(
            "Checkout initiated",
            extra={"request_id": request_id, "user_urn": current.urn}
        )

        redis_client = redis.from_url(settings.REDIS_URL)

        # extracting discount related parameters from Redis
        n_from_redis = await redis_client.get("VALUE_OF_N")
        n = int(n_from_redis) if n_from_redis else None

        nth_order_discount_percentage = await redis_client.get("VALUE_OF_NTH_ORDER_DISCOUNT_PERCENTAGE")
        nth_order_discount_percentage = int(nth_order_discount_percentage) if nth_order_discount_percentage else DEFAULT_DISCOUNT_PERCENTAGE

        logger.info(
            "Fetched VALUE_OF_N and VALUE_OF_NTH_ORDER_DISCOUNT_PERCENTAGE from Redis",
            extra={"request_id": request_id, "value": n, "percentage": nth_order_discount_percentage}
        )

        async with async_session() as session:
            
            # extracting all pending items from DB
            all_pending_items_query = await session.exec(
                select(Item).where(Item.owner_urn == current.urn, Item.status == ItemStatus.PENDING)
            )
            items = all_pending_items_query.all()

            if not items:
                logger.warning(
                    "Checkout aborted — no pending items",
                    extra={"request_id": request_id, "user_urn": current.urn}
                )
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=ErrorResponse(
                        error="No items to checkout",
                        request_id=request_id
                    ).model_dump()
                )

            subtotal = sum((item.price * item.qty for item in items), Decimal(0))

            # checking if the current order is the nth global order
            overall_orders_query = await session.exec(select(Order))
            total_orders_global = len(overall_orders_query.all())

            is_order_globally_nth = (n is not None and (total_orders_global + 1) % n == 0)

            logger.info(
                "Global order evaluation",
                extra={
                    "request_id": request_id,
                    "current_global_orders": total_orders_global,
                    "is_order_globally_nth": is_order_globally_nth
                }
            )

            discount_amount = Decimal(0)
            applied_discount_code = None

            # discount application iff the current order is the nth global order
            if is_order_globally_nth:
                current_discount_code_from_redis = await redis_client.get("CURRENT_DISCOUNT_CODE")
                
                if current_discount_code_from_redis:
                    extracted_discount_code = current_discount_code_from_redis.decode()

                    if extracted_discount_code == payload.discount_code:
                        res = await session.exec(
                            select(DiscountCode).where(DiscountCode.code == extracted_discount_code)
                        )
                        discount_obj = res.one_or_none()

                        if discount_obj and not discount_obj.used:
                            discount_amount = subtotal * Decimal(nth_order_discount_percentage / 100)
                            applied_discount_code = extracted_discount_code

                            logger.info(
                                "Discount applied",
                                extra={
                                    "request_id": request_id,
                                    "amount": float(discount_amount),
                                    "code": applied_discount_code
                                }
                            )
                        else:
                            logger.warning(
                                "Discount code invalid/used — skipping",
                                extra={"request_id": request_id}
                            )
                    else:
                        logger.warning(
                            "Requested discount code does not match generated code — skipping",
                            extra={"request_id": request_id}
                        )

            total = subtotal - discount_amount

            # order creation
            order = Order(
                owner_urn=current.urn,
                subtotal=subtotal,
                discount_code=applied_discount_code,
                total=total
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)

            # marking all items as fulfilled
            for item in items:
                item.status = ItemStatus.FULFILLED
                item.order_urn = order.urn
                item.fulfilled_at = datetime.now(timezone.utc)

            await session.commit()

            # marking discount code as unusable for future use
            if is_order_globally_nth and applied_discount_code:
                res = await session.exec(
                    select(DiscountCode).where(DiscountCode.code == applied_discount_code)
                )
                discount_obj = res.one_or_none()

                if discount_obj and not discount_obj.used:
                    discount_obj.used = True
                    discount_obj.user_urn = current.urn
                    discount_obj.order_urn = order.urn
                    await session.commit()

                    logger.info(
                        "Marked discount code as used",
                        extra={
                            "request_id": request_id,
                            "discount_code": applied_discount_code,
                            "order_urn": order.urn
                        }
                    )

        return CheckoutResponse(
            order_urn=order.urn,
            subtotal=float(subtotal),
            discount=float(discount_amount),
            total=float(total),
            applied_discount_code=applied_discount_code,
            is_order_globally_nth=is_order_globally_nth,
            request_id=request_id
        )
    
    except Exception as exception:
        logger.exception(
            "/checkout failed due to an exception",
            extra={"error": str(exception), "request_id": request_id}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="/checkout failed",
                request_id=request_id
            ).model_dump()
        )
