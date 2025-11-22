import uuid
from datetime import datetime, timedelta, timezone
from typing import Union

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import case, func
from sqlmodel import select

from app.auth import (create_jwt, get_current_admin, hash_password,
                      verify_password)
from app.core.config import settings
from app.core.constants import (DEFAULT_DISCOUNT_PERCENTAGE, ItemStatus,
                                TokenStatus)
from app.core.logging_setup import get_logger
from app.db import async_session
from app.models import Admin, DiscountCode, EndUser, Item, Order, Token
from app.schemas import (AdminCreateRequest, AdminCreateResponse,
                         AdminLoginRequest, AdminLoginResponse,
                         AdminLogoutResponse, DiscountCodesResponse,
                         DiscountNUpdateRequest, DiscountNUpdateResponse,
                         ErrorResponse, OrderSummary, SummaryResponse)

# from traceback import format_exc


router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/admins",
    response_model=Union[AdminCreateResponse, ErrorResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_admin(
    payload: AdminCreateRequest,
    request: Request,
    current_admin=Depends(get_current_admin),
):
    """
    Create a new admin user.

    Parameters:
    - payload: AdminCreateRequest containing username and password
    - request: Request object containing request_id
    - current_admin: Admin object containing the currently authenticated admin

    Returns:
    - AdminCreateResponse containing the new admin's URN and request_id on success
    - ErrorResponse containing error and request_id on failure

    Raises:
    - HTTPException with status code 409 and error "Username already taken" if username is already taken
    - HTTPException with status code 500 and error "/admins failed" if an exception occurs during the request
    """
    
    request_id = request.state.request_id

    try:
        logger.info(
            "Admin registration request received",
            extra={"request_id": request_id},
        )

        async with async_session() as session:

            # checking if username already taken
            exists_query = select(
                func.exists(
                    select(Admin.id)
                    .where(Admin.username == payload.username)
                    .scalar_subquery()
                )
            )

            exists = (await session.exec(exists_query)).first()

            if exists:
                logger.warning(
                    "Admin registration failed — username taken",
                    extra={"request_id": request_id},
                )
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content=ErrorResponse(
                        error="Username already taken",
                        request_id=request_id
                    ).model_dump()
                )

            # creating new admin
            new_admin = Admin(
                username=payload.username,
                hashed_password=hash_password(payload.password),
            )
            session.add(new_admin)
            await session.commit()
            await session.refresh(new_admin)

        logger.info(
            "Admin registered successfully",
            extra={"request_id": request_id, "new_admin_urn": new_admin.urn},
        )

        return AdminCreateResponse(
            urn=new_admin.urn,
            request_id=request_id,
        )

    except Exception as exception:
        logger.exception(
            "/admins failed due to an exception",
            extra={"error": str(exception), "request_id": request_id},
        )
    
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="/admins failed",
                request_id=request_id
            ).model_dump()
        )


@router.post(
    "/auth/admin/login",
    response_model=Union[AdminLoginResponse, ErrorResponse],
)
async def login_admin(payload: AdminLoginRequest, request: Request):
    """
    Login an admin using username and password.

    Parameters:
    - payload: AdminLoginRequest containing username and password
    - request: Request object containing request_id

    Returns:
    - AdminLoginResponse containing access_token and request_id on success
    - ErrorResponse containing error and request_id on failure

    Raises:
    - HTTPException with status code 401 and error "Invalid credentials" if username or password is invalid
    - HTTPException with status code 500 and error "/auth/admin/login failed" if an exception occurs during the request
    """

    request_id = request.state.request_id

    try:
        logger.info(
            "Admin login request recieved",
            extra={"request_id": request_id}
        )

        # checking if admin credentials correct
        async with async_session() as session:
            result = await session.exec(select(Admin).where(Admin.username == payload.username))
            # working setup:
            # admin = result.one_or_none()

            row = result.first()
            admin = row[0] if isinstance(row, tuple) else row

        if not admin or not verify_password(payload.password, admin.hashed_password):
            logger.warning(
                "Admin login failed — invalid credentials",
                extra={"request_id": request_id}
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=ErrorResponse(
                    error="Invalid credentials",
                    request_id=request_id
                ).model_dump()
            )
            
        # creating token and JWT
        token = create_jwt(admin.urn, is_admin=True, expires_seconds=3600)

        async with async_session() as session:
            db_token = Token(
                token=token,
                owner_urn=admin.urn,
                status=TokenStatus.ACTIVE,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=3600),
            )
            session.add(db_token)
            await session.commit()

        logger.info(
            "Admin logged in successfully",
            extra={"request_id": request_id, "admin_urn": admin.urn}
        )

        return AdminLoginResponse(access_token=token, request_id=request_id)
    
    except Exception as exception:
        logger.exception(
            "/auth/admin/login failed due to an exception",
            extra={"error": str(exception), "request_id": request_id}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="/auth/admin/login failed",
                request_id=request_id
            ).model_dump()
        )


@router.post(
    "/auth/admin/logout",
    response_model=Union[AdminLogoutResponse, ErrorResponse],
)
async def logout_admin(
    request: Request, 
    current=Depends(get_current_admin)
):
    """
    Logs out an admin user.

    Parameters:
    - request: Request object containing the request_id

    Returns:
    - AdminLogoutResponse containing message and request_id on success
    - ErrorResponse containing error and request_id on failure

    Raises:
    - HTTPException with status code 401 and error "Authorization header missing" if Authorization header is missing
    - HTTPException with status code 401 and error "Token missing" if token is missing
    - HTTPException with status code 401 and error "Token not found or already logged out" if token is not found in DB
    - HTTPException with status code 500 and error "/auth/admin/logout failed" if an exception occurs during the request
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
            "Admin logged out successfully",
            extra={
                "request_id": request_id,
                "admin_urn": current.urn,
                "token": stringified_token
            }
        )

        return AdminLogoutResponse(
            message="Admin logged out successfully",
            request_id=request_id
        )

    except Exception as exception:
        logger.exception(
            "/auth/admin/logout failed due to exception",
            extra={"error": str(exception), "request_id": request_id}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="/auth/admin/logout failed",
                request_id=request_id
            ).model_dump()
        )


@router.post(
    "/admin/discount-codes",
    response_model=Union[DiscountCodesResponse, ErrorResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_discount_code(request: Request, admin=Depends(get_current_admin)):
    """
    Generates a new discount code for end users.

    Parameters:
    - request: Request object containing the request_id
    - admin: Admin object containing the currently authenticated admin

    Returns:
    - DiscountCodesResponse containing the newly generated discount code and request_id on success
    - ErrorResponse containing error and request_id on failure

    Raises:
    - HTTPException with status code 500 and error "/admin/discount-codes failed" if an exception occurs during the request
    """

    request_id = request.state.request_id

    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        code = str(uuid.uuid4())[:8]

        logger.info(
            f"Admin generating discount code: {code}",
            extra={"request_id": request_id}
        )

        # storing discount code in DB
        async with async_session() as session:
            discount_code = DiscountCode(code=code, issued_at=datetime.now(timezone.utc))
            session.add(discount_code)
            await session.commit()

        # Store in redis as the currently active code
        await redis_client.set("CURRENT_DISCOUNT_CODE", code)

        logger.info(
            f"Discount code generated and stored in Redis: {code}",
            extra={"request_id": request_id}
        )

        return DiscountCodesResponse(code=code, request_id=request_id)
    
    except Exception as exception:
        logger.exception(
            "/admin/discount-codes failed due to an exception",
            extra={"error": str(exception), "request_id": request_id}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="/admin/discount-codes failed",
                request_id=request_id
            ).model_dump()
        )


@router.get(
    "/admin/reports/summary",
    response_model=Union[SummaryResponse, ErrorResponse],
)
async def get_admin_summary(request: Request, admin=Depends(get_current_admin)):
    """
    Retrieves a summary of the admin's operations.

    Parameters:
    - request: Request object containing the request_id
    - admin: Admin object containing the currently authenticated admin

    Returns:
    - SummaryResponse containing the summary of the admin's operations and request_id on success
    - ErrorResponse containing error and request_id on failure

    Raises:
    - HTTPException with status code 500 and error "/admin/reports/summary failed" if an exception occurs during the request
    """
    
    request_id = request.state.request_id

    try:
        logger.info("Generating admin summary", extra={"request_id": request_id})

        async with async_session() as session:

            # top level details via grouping
            global_query = select(
                # users served
                (select(func.count(EndUser.id))).label("users_served"),

                # orders completed
                (select(func.count(Order.id))).label("orders_completed"),

                # total purchase amount (SUM of original subtotals)
                (select(func.coalesce(func.sum(Order.subtotal), 0))).label("total_purchase_amount"),

                # total discount amount (SUM of all discounts)
                (select(func.coalesce(func.sum(Order.subtotal - Order.total), 0))).label("total_discount_amount"),

                # total items fulfilled (JOIN necessary here)
                func.coalesce(
                    func.sum(
                        case((Item.status == ItemStatus.FULFILLED, 1), else_=0)
                    ),
                    0
                ).label("items_fulfilled"),

                # utilized discount codes
                func.coalesce(
                    func.array_remove(
                        (select(func.array_agg(func.distinct(Order.discount_code)))
                        .select_from(Order)),
                        None
                    ),
                    []
                ).label("utilized_discount_codes"),
            ).select_from(Item)

            global_result = (await session.exec(global_query)).one()

            users_served = global_result.users_served
            orders_completed = global_result.orders_completed
            total_purchase_amount = float(global_result.total_purchase_amount)
            total_discount_amount = float(global_result.total_discount_amount)
            items_fulfilled = global_result.items_fulfilled
            utilized_discount_codes = global_result.utilized_discount_codes or []

            # summary per order
            order_query = (
                select(
                    Order.urn,
                    Order.subtotal,
                    Order.total,
                    Order.discount_code,

                    func.coalesce(
                        func.sum(
                            case((Item.status == ItemStatus.FULFILLED, 1), else_=0)
                        ),
                        0
                    ).label("items_fulfilled"),
                )
                .join(Item, Item.order_urn == Order.urn, isouter=True)
                .group_by(Order.urn, Order.subtotal, Order.total, Order.discount_code)
            )

            order_rows = (await session.exec(order_query)).all()

            order_summaries = [
                OrderSummary(
                    order_urn=row[0],
                    subtotal=float(row[1]),
                    discount=float(row[1] - row[2]),   # subtotal - total
                    total=float(row[2]),
                    applied_discount_code=row[3],
                    items_fulfilled=row[4],
                )
                for row in order_rows
            ]

        logger.info(
            "Admin summary",
            extra={
                "request_id": request_id,
                "users_served": users_served,
                "orders_completed": orders_completed,
                "items_fulfilled": items_fulfilled,
                "total_purchase_amount": total_purchase_amount,
                "total_discount_amount": total_discount_amount,
                "utilized_codes_count": len(utilized_discount_codes),
                "order_summary_count": len(order_summaries),
            }
        )

        return SummaryResponse(
            users_served=users_served,
            items_fulfilled=items_fulfilled,
            total_purchase_amount=total_purchase_amount,
            utilized_discount_codes=utilized_discount_codes,
            total_discount_amount=total_discount_amount,
            orders_completed=orders_completed,
            orders=order_summaries,
            request_id=request_id,
        )

    except Exception as exception:
        logger.exception(
            "/admin/reports/summary failed",
            extra={"error": str(exception), "request_id": request_id}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="/admin/reports/summary failed",
                request_id=request_id
            ).model_dump()
        )
  

@router.put(
    "/admin/config/discount-n",
    response_model=Union[DiscountNUpdateResponse, ErrorResponse],
)
async def update_discount_n(payload: DiscountNUpdateRequest, request: Request, admin=Depends(get_current_admin)):
    
    """
    Update the value of N and the discount percentage for Nth order trigger.

    Parameters:
    - payload: DiscountNUpdateRequest containing the new value of N and discount percentage
    - request: Request object containing the request_id
    - admin: Admin object containing the currently authenticated admin

    Returns:
    - DiscountNUpdateResponse containing the updated message, request_id on success
    - ErrorResponse containing error and request_id on failure

    Raises:
    - HTTPException with status code 500 and error "/admin/config/discount-n failed" if an exception occurs during the request
    """

    request_id = request.state.request_id

    try:
        n = payload.n
        nth_order_discount_percentage = payload.discount_percentage or DEFAULT_DISCOUNT_PERCENTAGE

        # setting parameters in Redis
        redis_client = redis.from_url(settings.REDIS_URL)
        await redis_client.set("VALUE_OF_N", n)
        await redis_client.set("VALUE_OF_NTH_ORDER_DISCOUNT_PERCENTAGE", nth_order_discount_percentage)

        logger.info("VALUE_OF_N and VALUE_OF_NTH_ORDER_DISCOUNT_PERCENTAGE updated", extra={"request_id": request_id, "value": n, "percentage": nth_order_discount_percentage})

        suffix = "th"
        if n == 1:
            suffix = "st"
        elif n == 2:
            suffix = "nd"
        elif n == 3:
            suffix = "rd"

        return DiscountNUpdateResponse(message=f"{nth_order_discount_percentage}% discount applies every {n}{suffix} order", request_id=request_id)
    
    except Exception as exception:
        logger.exception(
            "/admin/config/discount-n failed due to an exception",
            extra={"error": str(exception), "request_id": request_id}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="/admin/config/discount-n failed",
                request_id=request_id
            ).model_dump()
        )