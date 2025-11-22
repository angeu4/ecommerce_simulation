from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.constants import REQUEST_ID_SYSTEM
from app.core.exceptions import AuthError
from app.core.logging_setup import get_logger
from app.db import create_db_and_tables
from app.middleware.api_logger import ApiLoggerMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.routers import admin, ui, user
from app.schemas import HealthResponse

logger = get_logger(__name__)

app = FastAPI(
    title="Ecommerce simulation",
    description="Ecommerce simulation",
    version="1.0.0",
    validate_response=True
)

# -------------------------
# CORS Middleware
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Logging Middlewares
# -------------------------
app.add_middleware(ApiLoggerMiddleware)
app.add_middleware(RequestIDMiddleware)


# -------------------------
# Startup Event
# -------------------------
@app.on_event("startup")
async def on_startup():
    """
    Event handler for FastAPI startup event.

    Logs a message when the backend is starting up and another message when it is complete.
    Also creates the database and tables if they do not exist.

    :param None:
    :return None:
    """
    
    logger.info("Starting backend...", extra={"request_id": REQUEST_ID_SYSTEM})
    await create_db_and_tables()
    logger.info("Backend startup complete.", extra={"request_id": REQUEST_ID_SYSTEM})


# -------------------------
# Routers
# -------------------------
app.include_router(user.router)
app.include_router(admin.router)
app.include_router(ui.router)


@app.get(
    "/health",
    response_model=HealthResponse,
)
async def health_check():
    """
    Returns a health check response.

    The health check response contains a status field which is always set to "Systems healthy".
    The request_id field is set to the REQUEST_ID_SYSTEM constant.

    :return HealthResponse: The health check response.
    :rtype HealthResponse:
    """
    
    return HealthResponse(status="Systems healthy", request_id=REQUEST_ID_SYSTEM)


@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, auth_error: AuthError):
    """
    Handles AuthError exceptions.

    When an AuthError exception is raised, this handler is called.
    It returns a JSONResponse with a status code of 401 and a content
    containing the error message and the request_id.

    The request_id field is set to the REQUEST_ID_SYSTEM constant if no
    request_id is found in the request state.

    :param request: The request object containing the request_id
    :param auth_error: The AuthError exception containing the error message
    :return JSONResponse: The response containing the error message and request_id
    :rtype JSONResponse:
    """

    request_id = getattr(request.state, "request_id", REQUEST_ID_SYSTEM)
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "error": auth_error.message,
            "request_id": request_id
        }
    )
