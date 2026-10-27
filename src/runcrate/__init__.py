"""Runcrate Python SDK — Official client for the Runcrate API."""

from runcrate._client import AsyncRuncrate, Runcrate
from runcrate._exceptions import (
    ApiError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    UnprocessableEntityError,
    ConnectionError,
    InsufficientCreditsError,
    InternalServerError,
    JobWaitTimeoutError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    RuncrateError,
    TimeoutError,
)
from runcrate._pagination import PaginatedResponse

__version__ = "0.5.0"

__all__ = [
    "AsyncRuncrate",
    "Runcrate",
    # Exceptions
    "ApiError",
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "UnprocessableEntityError",
    "ConnectionError",
    "InsufficientCreditsError",
    "InternalServerError",
    "JobWaitTimeoutError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "RuncrateError",
    "TimeoutError",
    # Pagination
    "PaginatedResponse",
    # Version
    "__version__",
]
