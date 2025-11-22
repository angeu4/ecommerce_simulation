import re
from unittest.mock import patch

from app.core.constants import REQUEST_ID_SYSTEM
from app.utils.urn import generate_urn

UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


def test_generate_urn_format():
    """
    Verify that generate_urn() returns a URN with a valid UUID format.

    The test ensures that the URN starts with the correct prefix, and that
    the UUID part of the URN matches the expected regular expression.
    """
    
    urn = generate_urn("order")

    assert urn.startswith("urn:order:")
    uuid_part = urn.split(":")[-1]
    assert UUID_REGEX.match(uuid_part)


def test_generate_urn_unique():
    """
    Verify that generate_urn() returns a unique URN each time it is called.

    The test ensures that two calls to generate_urn() with the same prefix
    will result in two different URNs.
    """
    
    urn1 = generate_urn("x")
    urn2 = generate_urn("x")
    assert urn1 != urn2


def test_generate_urn_respects_prefix():
    """
    Verify that generate_urn() respects the provided prefix.

    The test ensures that the URN returned by generate_urn() starts with
    the provided prefix.
    """
    
    urn = generate_urn("user")
    assert urn.split(":")[1] == "user"


def test_generate_urn_logs_info():
    """Ensure logger is called with correct message + request_id."""
    with patch("app.utils.urn.logger") as mock_logger:
        urn = generate_urn("abc")

        mock_logger.info.assert_called_once()
        call_args, call_kwargs = mock_logger.info.call_args

        # Validate log message contains full URN
        assert "Generated URN" in call_args[0]
        assert urn in call_args[0]

        # Validate request_id metadata
        assert call_kwargs["extra"]["request_id"] == REQUEST_ID_SYSTEM
