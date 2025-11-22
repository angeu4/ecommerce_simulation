from enum import Enum


class TokenStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class ItemStatus(str, Enum):
    PENDING = "PENDING"
    FULFILLED = "FULFILLED"


FILE_BASED_LOG_MAX_SIZE: int = 10 * 1024 * 1024  # 10 MB
FILE_BASED_LOG_MAX_COUNT: int = 5


UTF_ENCODING: str = "utf-8"


REQUEST_ID_SYSTEM: str = "SYSTEM"
REQUEST_ID_NO_REQUEST_ID: str = "NO-REQUEST-ID"


DEFAULT_DISCOUNT_PERCENTAGE: int = 10