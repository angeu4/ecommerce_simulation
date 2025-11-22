import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch_original(self, request, call_next):
        """
        Attaches a request_id to each request and response.

        The request_id is generated randomly using uuid.uuid4() and is
        stored in the request.state dictionary. It is then attached
        to the response headers.

        This allows the request_id to be accessed in the request and
        response, and can be used to trace the lifecycle of the
        request.
        """

        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    async def dispatch(self, request: Request, call_next):
        """
        Attaches a request_id to each request and response.

        The request_id is generated randomly using uuid.uuid4() and is
        stored in the request.state dictionary. It is then attached
        to the response headers.

        This allows the request_id to be accessed in the request and
        response, and can be used to trace the lifecycle of the
        request.
        """

        # if client provides one, use it. Otherwise generate one.
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Attach to request.state
        request.state.request_id = request_id

        # Continue request processing
        response = await call_next(request)

        # Attach request id to response
        response.headers["X-Request-ID"] = request_id

        # Preserve other incoming custom headers (optional but your test requires it)
        for header, value in request.headers.items():
            if header.lower().startswith("x-") and header.lower() != "x-request-id":
                response.headers[header] = value

        return response