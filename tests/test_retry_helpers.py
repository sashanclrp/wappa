"""Tests for wappa.resilience retry helpers and transient-error classification.

Observable behaviour only: how many times a wrapped coroutine runs, which
exception surfaces to the caller, and how each error class is classified.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from wappa.resilience import (
    RetryPolicy,
    is_transient_db_error,
    is_transient_http_error,
    retry_async,
    retry_transient_db,
    retry_transient_http,
)

NO_WAIT = RetryPolicy(attempts=3, initial_delay=0, jitter=0)


def _status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test/resource")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


# ---------------------------------------------------------------------------
# HTTP classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectTimeout("timeout"),
        httpx.ReadTimeout("timeout"),
        httpx.ConnectError("refused"),
        httpx.PoolTimeout("pool"),
        httpx.RemoteProtocolError("truncated"),
        ConnectionResetError(),
    ],
)
def test_transport_failures_are_transient_http_errors(error: Exception) -> None:
    assert is_transient_http_error(error) is True


@pytest.mark.parametrize("status_code", [408, 425, 429, 500, 502, 503, 504])
def test_retryable_status_codes_are_transient(status_code: int) -> None:
    assert is_transient_http_error(_status_error(status_code)) is True


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 409, 422])
def test_client_error_status_codes_are_not_transient(status_code: int) -> None:
    assert is_transient_http_error(_status_error(status_code)) is False


def test_non_http_exception_is_not_a_transient_http_error() -> None:
    assert is_transient_http_error(ValueError("bad payload")) is False


# ---------------------------------------------------------------------------
# Database classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        ConnectionRefusedError(),
        ConnectionResetError(),
        OSError("network is unreachable"),
        RuntimeError("server closed the connection unexpectedly"),
        RuntimeError("could not connect to server"),
        RuntimeError("name or service not known"),
    ],
)
def test_connectivity_failures_are_transient_db_errors(error: Exception) -> None:
    assert is_transient_db_error(error) is True


def test_pool_checkout_timeout_is_not_transient() -> None:
    # SQLAlchemy's pool timeout message contains "connection timed out", which
    # would otherwise match a connectivity pattern. The pool is drained, so
    # retrying makes saturation worse.
    error = SQLAlchemyTimeoutError(
        "QueuePool limit reached, connection timed out, timeout 30.00"
    )
    assert is_transient_db_error(error) is False


@pytest.mark.parametrize(
    "error",
    [
        ValueError("syntax error at or near SELECT"),
        RuntimeError("duplicate key value violates unique constraint"),
    ],
)
def test_query_failures_are_not_transient_db_errors(error: Exception) -> None:
    assert is_transient_db_error(error) is False


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transient_http_failure_is_retried_until_it_succeeds() -> None:
    attempts = 0

    @retry_transient_http(policy=NO_WAIT)
    async def call() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("refused")
        return "ok"

    assert await call() == "ok"
    assert attempts == 3


@pytest.mark.asyncio
async def test_transient_http_failure_raises_original_error_after_last_attempt() -> (
    None
):
    attempts = 0

    @retry_transient_http(policy=NO_WAIT)
    async def call() -> None:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("still refused")

    with pytest.raises(httpx.ConnectError, match="still refused"):
        await call()
    assert attempts == NO_WAIT.attempts


@pytest.mark.asyncio
async def test_non_transient_http_failure_is_not_retried() -> None:
    attempts = 0

    @retry_transient_http(policy=NO_WAIT)
    async def call() -> None:
        nonlocal attempts
        attempts += 1
        raise _status_error(404)

    with pytest.raises(httpx.HTTPStatusError):
        await call()
    assert attempts == 1


@pytest.mark.asyncio
async def test_transient_db_failure_is_retried() -> None:
    attempts = 0

    @retry_transient_db(policy=NO_WAIT)
    async def query() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ConnectionResetError("connection reset by peer")
        return "row"

    assert await query() == "row"
    assert attempts == 2


@pytest.mark.asyncio
async def test_non_transient_db_failure_is_not_retried() -> None:
    attempts = 0

    @retry_transient_db(policy=NO_WAIT)
    async def query() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("duplicate key value violates unique constraint")

    with pytest.raises(ValueError):
        await query()
    assert attempts == 1


@pytest.mark.asyncio
async def test_cancellation_is_never_retried() -> None:
    attempts = 0

    @retry_async(policy=NO_WAIT, retry_on=lambda _: True)
    async def call() -> None:
        nonlocal attempts
        attempts += 1
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await call()
    assert attempts == 1


@pytest.mark.asyncio
async def test_single_attempt_policy_disables_retry() -> None:
    attempts = 0

    @retry_transient_http(policy=RetryPolicy(attempts=1, initial_delay=0, jitter=0))
    async def call() -> None:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("refused")

    with pytest.raises(httpx.ConnectError):
        await call()
    assert attempts == 1


@pytest.mark.asyncio
async def test_decorator_preserves_arguments_and_identity() -> None:
    @retry_transient_http(policy=NO_WAIT)
    async def add(left: int, right: int = 0) -> int:
        """Docstring is preserved."""
        return left + right

    assert await add(2, right=3) == 5
    assert add.__name__ == "add"
    assert add.__doc__ == "Docstring is preserved."


# ---------------------------------------------------------------------------
# Policy validation and backoff bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"attempts": 0},
        {"initial_delay": -1},
        {"multiplier": 0.5},
        {"jitter": 1.5},
    ],
)
def test_invalid_policies_are_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)


def test_backoff_grows_and_is_capped_by_max_delay() -> None:
    policy = RetryPolicy(
        attempts=6, initial_delay=1, multiplier=2, max_delay=4, jitter=0
    )
    assert [policy.delay_for(i) for i in range(5)] == [1, 2, 4, 4, 4]


def test_jitter_stays_within_the_configured_band() -> None:
    policy = RetryPolicy(attempts=3, initial_delay=1, multiplier=1, jitter=0.25)
    delays = [policy.delay_for(0) for _ in range(200)]

    assert all(0.75 <= delay <= 1.25 for delay in delays)
    assert len(set(delays)) > 1  # actually randomised
