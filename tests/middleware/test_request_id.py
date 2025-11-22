import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.middleware.request_id import RequestIDMiddleware

UUID_REGEX = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
    re.IGNORECASE,
)


def build_test_app():
    """
    Builds a minimal FastAPI app with only the RequestID middleware and one route.
    """
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    async def ping(request: Request):
        return {"request_id": request.state.request_id}

    return app


# -------------------------------------------------------------
# TEST 1: X-Request-ID should be echoed back if provided
# -------------------------------------------------------------
def test_request_id_preserved_if_sent():
    """
    Verify that the RequestID middleware echoes back the X-Request-ID header if present.

    This test ensures that the request_id is preserved and passed to the endpoint.
    """
    
    app = build_test_app()
    client = TestClient(app)

    custom_id = "REQ-12345"

    r = client.get("/ping", headers={"X-Request-ID": custom_id})
    assert r.status_code == 200

    # Response header contains same request id
    assert r.headers["X-Request-ID"] == custom_id

    # Endpoint sees the same value
    assert r.json()["request_id"] == custom_id


# -------------------------------------------------------------
# TEST 2: Middleware should generate a UUID if header is missing
# -------------------------------------------------------------
def test_request_id_generated_if_missing():
    """
    Verify that the RequestID middleware generates a UUID if the X-Request-ID header is missing.

    This test ensures that the request_id is generated and passed to the endpoint.
    """
    
    app = build_test_app()
    client = TestClient(app)

    r = client.get("/ping")
    assert r.status_code == 200

    generated = r.headers.get("X-Request-ID")
    assert generated is not None
    assert UUID_REGEX.match(generated)  # verify valid UUID format

    # Ensure endpoint received same UUID
    assert r.json()["request_id"] == generated


# -------------------------------------------------------------
# TEST 3: Generated request ID must be different per request
# -------------------------------------------------------------
def test_generated_request_id_is_unique():
    """
    Verify that the RequestID middleware generates a unique request_id for each request.

    This test ensures that the request_id is different for each request.
    """
    
    app = build_test_app()
    client = TestClient(app)

    r1 = client.get("/ping")
    r2 = client.get("/ping")

    id1 = r1.headers["X-Request-ID"]
    id2 = r2.headers["X-Request-ID"]

    assert id1 != id2
    assert UUID_REGEX.match(id1)
    assert UUID_REGEX.match(id2)


# -------------------------------------------------------------
# TEST 4: Middleware does not remove or modify unrelated headers
# -------------------------------------------------------------
def test_middleware_preserves_other_headers():
    """
    Verify that the RequestID middleware preserves other, unrelated headers.

    This test ensures that the middleware does not remove or modify headers that are not related to the request_id.
    """
    
    app = build_test_app()
    client = TestClient(app)

    r = client.get("/ping", headers={"X-Custom": "abc"})
    assert r.status_code == 200
    assert r.headers["X-Custom"] == "abc"


# -------------------------------------------------------------
# TEST 5: request.state.request_id exists inside route handler
# -------------------------------------------------------------
def test_request_id_attached_to_request_state():
    """
    Verify that the request_id is attached to the request.state inside the route handler.

    This test ensures that the request_id is available inside the route handler.
    """
    
    app = build_test_app()
    client = TestClient(app)

    r = client.get("/ping")
    assert r.status_code == 200

    request_id = r.json()["request_id"]
    assert request_id is not None
    assert UUID_REGEX.match(request_id)
