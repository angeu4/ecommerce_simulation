import json
import logging

from app.core.logging_setup import JSONFormatter, file_handler, get_logger


# -------------------------------------------------------
# Test JSONFormatter.format() basic fields
# -------------------------------------------------------
def test_json_formatter_basic_fields():
    """
    Verify that JSONFormatter formats the basic fields of a LogRecord:

    - message
    - level
    - logger
    - timestamp

    This test ensures that the default fields are present in the JSON log entry.
    """
    
    formatter = JSONFormatter()

    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello world",
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["message"] == "hello world"
    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert "timestamp" in data


# -------------------------------------------------------
# Test JSONFormatter with request_id
# -------------------------------------------------------
def test_json_formatter_with_request_id():
    """
    Verify that JSONFormatter formats the request_id field of a LogRecord.

    This test ensures that the request_id field is present in the JSON log entry.
    """
    
    formatter = JSONFormatter()

    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=20,
        msg="test message",
        args=(),
        exc_info=None,
    )
    record.request_id = "REQ-123"

    output = formatter.format(record)
    data = json.loads(output)

    assert data["request_id"] == "REQ-123"


# -------------------------------------------------------
# Test JSONFormatter with extra structured fields
# -------------------------------------------------------
def test_json_formatter_extra_fields():
    """
    Verify that JSONFormatter formats extra structured fields of a LogRecord.

    This test ensures that additional fields attached to the LogRecord
    are present in the JSON log entry.
    """
    
    formatter = JSONFormatter()

    record = logging.LogRecord(
        name="test.logger",
        level=logging.WARNING,
        pathname=__file__,
        lineno=30,
        msg="warning occurred",
        args=(),
        exc_info=None,
    )
    record.user_urn = "urn:user:abc"
    record.cart_id = 111

    output = formatter.format(record)
    data = json.loads(output)

    assert data["user_urn"] == "urn:user:abc"
    assert data["cart_id"] == 111


# -------------------------------------------------------
# Test RotatingFileHandler configuration
# -------------------------------------------------------
def test_file_handler_is_rotating():
    """
    Verify that the RotatingFileHandler has been configured with a maxBytes
    and backupCount greater than 0. This test ensures that the logging
    configuration will rotate the log files when the maxBytes limit is reached
    and that the backupCount limit is respected.
    """

    assert hasattr(file_handler, "maxBytes")
    assert hasattr(file_handler, "backupCount")
    assert file_handler.maxBytes > 0
    assert file_handler.backupCount > 0


# -------------------------------------------------------
# Test that logging writes JSON to file handler
# -------------------------------------------------------
def test_json_log_written(tmp_path, monkeypatch):
    """
    Ensures JSON log writes to a temporary test file instead of real /app/logs.
    """

    from app.core.logging_setup import JSONFormatter, RotatingFileHandler

    test_log_file = tmp_path / "test.log"
    test_log_file.parent.mkdir(parents=True, exist_ok=True)

    # Create a test-specific handler
    test_handler = RotatingFileHandler(
        str(test_log_file),
        maxBytes=1024 * 1024,
        backupCount=1,
        encoding="utf-8"
    )
    test_handler.setFormatter(JSONFormatter())

    logger = get_logger("write.test.logger")
    logger.handlers = []          # isolate from global handlers
    logger.addHandler(test_handler)
    logger.setLevel(logging.INFO)

    logger.info("log entry", extra={"request_id": "REQ999"})

    # Force the handler to write
    test_handler.flush()

    # Now it WILL exist
    contents = test_log_file.read_text().strip()
    data = json.loads(contents)

    assert data["message"] == "log entry"
    assert data["request_id"] == "REQ999"
