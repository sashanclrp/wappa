"""Transient-failure classification for HTTP and database errors.

Classification is the interesting part of a retry helper: retrying a
non-transient failure turns a fast error into a slow one, and refusing to
retry a transient failure turns a blip into an outage. These predicates are
the single place Wappa decides which is which, and they are reused by the
database session manager, transport adapters, webhook processors, and
credential stores.
"""

from __future__ import annotations

import asyncio
import socket
import ssl

import httpx

# HTTP status codes worth retrying. 4xx codes are excluded except the two
# that explicitly mean "try again": 408 Request Timeout and 429 Too Many
# Requests. Everything else in the 4xx range is a client contract failure and
# will fail identically on retry.
TRANSIENT_HTTP_STATUS_CODES: frozenset[int] = frozenset(
    {408, 425, 429, 500, 502, 503, 504}
)

# Exception types that always mean "the call never got a clean answer".
_TRANSIENT_HTTP_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
    httpx.PoolTimeout,
    ssl.SSLError,
    socket.gaierror,
    ConnectionError,
    asyncio.TimeoutError,
)

# Builtin/OS-level error types that indicate a transient database transport
# failure rather than a bad query or constraint violation.
TRANSIENT_DB_ERROR_TYPES: tuple[type[BaseException], ...] = (
    OSError,
    ConnectionError,
    ConnectionRefusedError,
    ConnectionResetError,
    TimeoutError,
)

# Driver error messages that indicate a transient connectivity failure. Driver
# exception hierarchies vary too much across asyncpg/psycopg/aiomysql to rely
# on types alone.
TRANSIENT_DB_ERROR_PATTERNS: tuple[str, ...] = (
    "connection refused",
    "connection reset",
    "connection timed out",
    "could not connect",
    "server closed the connection",
    "ssl connection has been closed",
    "network is unreachable",
    "no route to host",
    "name resolution failed",
    "name or service not known",
    "dns",
)


def is_transient_http_error(error: BaseException) -> bool:
    """Return True when an HTTP failure is worth retrying.

    Retryable: timeouts, connect/read/write failures, DNS and TLS failures,
    pool timeouts, and responses carrying a status in
    ``TRANSIENT_HTTP_STATUS_CODES``.

    Not retryable: any other 4xx (auth, validation, not-found), and any
    non-HTTP exception such as a payload ``ValueError``.
    """
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in TRANSIENT_HTTP_STATUS_CODES
    return isinstance(error, _TRANSIENT_HTTP_EXCEPTIONS)


def is_transient_db_error(error: BaseException) -> bool:
    """Return True when a database failure is worth retrying.

    Retryable: connection refused/reset, DNS failures, dropped server
    connections, and OS-level socket errors.

    Not retryable: SQLAlchemy pool checkout timeouts (the pool is already
    drained — retrying parks the request and saturates the pooler further),
    integrity violations, programming errors, and anything else whose message
    does not match a known connectivity pattern.
    """
    if _is_pool_timeout(error):
        return False
    if isinstance(error, TRANSIENT_DB_ERROR_TYPES):
        return True
    message = str(error).lower()
    return any(pattern in message for pattern in TRANSIENT_DB_ERROR_PATTERNS)


def _sqlalchemy_timeout_error() -> type[BaseException] | None:
    """Resolve SQLAlchemy's pool checkout timeout type without hard-importing it.

    Resolved once per process and cached, since the result never changes
    while the interpreter is running and this predicate runs on every
    database-error classification.
    """
    try:
        from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
    except ImportError:  # pragma: no cover - SQLAlchemy is an optional extra
        return None
    return SQLAlchemyTimeoutError


_SQLALCHEMY_TIMEOUT_ERROR = _sqlalchemy_timeout_error()


def _is_pool_timeout(error: BaseException) -> bool:
    """Detect SQLAlchemy's pool checkout timeout."""
    if _SQLALCHEMY_TIMEOUT_ERROR is None:
        return False
    return isinstance(error, _SQLALCHEMY_TIMEOUT_ERROR)
