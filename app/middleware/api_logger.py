import json
from datetime import datetime, timezone
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.constants import REQUEST_ID_NO_REQUEST_ID
from app.core.logging_setup import get_logger
from app.db import async_session
from app.models import ApiLog

logger = get_logger(__name__)


def mask_sensitive(data: Any) -> Any:
    """
    Masks sensitive data in the given data structure.

    This function takes any data structure (dict, list, etc.)
    and returns a new data structure with sensitive data (password, pwd, pass)
    masked with "xxxxxx".

    :param data: The data structure to mask sensitive data in.
    :return: A new data structure with sensitive data masked.
    """
    
    SENSITIVE_KEYS = {"password", "pwd", "pass"}

    if isinstance(data, dict):
        return {
            key: ("xxxxxx" if key.lower() in SENSITIVE_KEYS else mask_sensitive(value))
            for key, value in data.items()
        }

    elif isinstance(data, list):
        return [mask_sensitive(item) for item in data]

    return data


class ApiLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        """
        Middleware to log incoming API requests.

        This middleware logs each incoming request with a request_id, endpoint, request payload, and HTTP status code.
        The request payload is masked for sensitive information such as passwords.

        :param request: The incoming request
        :param call_next: The next middleware in the call stack
        :return: The response from the next middleware
        """
        
        request_id = getattr(request.state, "request_id", None) or REQUEST_ID_NO_REQUEST_ID

        try:
            body_bytes = await request.body()
            body_str = body_bytes.decode() if body_bytes else ""

            # Try JSON masking
            try:
                json_body = json.loads(body_str)
                masked_json = mask_sensitive(json_body)
                body_str = json.dumps(masked_json, indent=2)
            except Exception:
                # Non-JSON body
                pass

        except Exception:
            body_str = ""

        # Emit console + file log
        logger.info(
            f"Incoming request: {request.method} {request.url.path}",
            extra={"request_id": request_id, "payload": body_str}
        )

        response: Response = await call_next(request)

        # Write ApiLog entry
        try:
            async with async_session() as session:
                entry = ApiLog(
                    request_id=request_id,
                    endpoint=request.url.path,
                    request_payload=body_str,
                    http_status_code=response.status_code,
                    created_at=datetime.now(timezone.utc)
                )
                session.add(entry)
                await session.commit()
        except Exception as e:
            logger.error(
                f"Failed to store API log: {e}",
                extra={"request_id": request_id}
            )

        return response
