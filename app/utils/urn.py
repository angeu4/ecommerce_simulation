import uuid

from app.core.constants import REQUEST_ID_SYSTEM
from app.core.logging_setup import get_logger

logger = get_logger(__name__)


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
    
    urn = f"urn:{prefix}:{uuid.uuid4()}"
    logger.info(f"Generated URN: {urn}", extra={"request_id": REQUEST_ID_SYSTEM})
    return urn
