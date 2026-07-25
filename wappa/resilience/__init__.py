"""Resilience primitives for transient integration failures.

Generic, transport-neutral retry helpers reusable by transport adapters,
webhook processors, credential stores, and external platform clients.

    from wappa.resilience import RetryPolicy, retry_transient_http

    @retry_transient_http(policy=RetryPolicy(attempts=5))
    async def call_provider(): ...
"""

from .classification import (
    TRANSIENT_DB_ERROR_PATTERNS,
    TRANSIENT_DB_ERROR_TYPES,
    TRANSIENT_HTTP_STATUS_CODES,
    is_transient_db_error,
    is_transient_http_error,
)
from .retry import (
    DEFAULT_RETRY_POLICY,
    RetryPolicy,
    retry_async,
    retry_transient_db,
    retry_transient_http,
)

__all__ = [
    "DEFAULT_RETRY_POLICY",
    "TRANSIENT_DB_ERROR_PATTERNS",
    "TRANSIENT_DB_ERROR_TYPES",
    "TRANSIENT_HTTP_STATUS_CODES",
    "RetryPolicy",
    "is_transient_db_error",
    "is_transient_http_error",
    "retry_async",
    "retry_transient_db",
    "retry_transient_http",
]
