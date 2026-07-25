"""Retry helpers for transient HTTP and database failures.

Usage:

    from wappa.resilience import retry_transient_http

    @retry_transient_http()
    async def fetch_credentials(client, url):
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

The decorated coroutine retries only failures classified as transient by
:mod:`wappa.resilience.classification`. Non-transient failures propagate
immediately, and the final attempt's exception always propagates unchanged so
callers keep the original traceback.
"""

from __future__ import annotations

import asyncio
import functools
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from wappa.core.logging.logger import get_logger

from .classification import is_transient_db_error, is_transient_http_error

logger = get_logger(__name__)


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff with jitter.

    Args:
        attempts: Total attempts including the first call. ``1`` disables retry.
        initial_delay: Delay in seconds before the second attempt.
        max_delay: Upper bound applied after backoff and jitter.
        multiplier: Exponential growth factor between attempts.
        jitter: Fraction of the computed delay randomised in ``±jitter`` to
            avoid synchronised retry storms across processes. ``0`` disables it.
    """

    attempts: int = 3
    initial_delay: float = 0.2
    max_delay: float = 5.0
    multiplier: float = 2.0
    jitter: float = 0.25

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be >= 1")
        if self.initial_delay < 0 or self.max_delay < 0:
            raise ValueError("delays must be non-negative")
        if self.multiplier < 1:
            raise ValueError("multiplier must be >= 1")
        if not 0 <= self.jitter <= 1:
            raise ValueError("jitter must be between 0 and 1")

    def delay_for(self, attempt: int) -> float:
        """Delay in seconds before the attempt following ``attempt`` (0-indexed)."""
        delay = self.initial_delay * (self.multiplier**attempt)
        if self.jitter:
            delay *= 1 + random.uniform(-self.jitter, self.jitter)
        return max(0.0, min(delay, self.max_delay))


DEFAULT_RETRY_POLICY = RetryPolicy()


def retry_async[**P, R](
    *,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    retry_on: Callable[[BaseException], bool],
    operation: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Retry a coroutine while ``retry_on`` classifies its failure as transient.

    Args:
        policy: Attempt count and backoff schedule.
        retry_on: Predicate deciding whether a raised exception is retryable.
        operation: Label used in retry warnings. Defaults to the function name.

    Returns:
        A decorator preserving the wrapped coroutine's signature.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        label = operation or func.__qualname__

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_attempt = policy.attempts - 1
            for attempt in range(policy.attempts):
                try:
                    return await func(*args, **kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    if attempt == last_attempt or not retry_on(error):
                        raise
                    delay = policy.delay_for(attempt)
                    logger.warning(
                        "%s failed (attempt %d/%d): %s. Retrying in %.2fs",
                        label,
                        attempt + 1,
                        policy.attempts,
                        error,
                        delay,
                    )
                    if delay:
                        await asyncio.sleep(delay)
            raise AssertionError("unreachable: retry loop exhausted without returning")

        return wrapper

    return decorator


def retry_transient_http[**P, R](
    *,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    operation: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Retry a coroutine on transient HTTP failures.

    See :func:`wappa.resilience.is_transient_http_error` for what counts as
    transient. Raise ``httpx.HTTPStatusError`` (via ``response.raise_for_status()``)
    inside the wrapped function for status-code retries to apply.
    """
    return retry_async(
        policy=policy, retry_on=is_transient_http_error, operation=operation
    )


def retry_transient_db[**P, R](
    *,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    operation: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Retry a coroutine on transient database connectivity failures.

    See :func:`wappa.resilience.is_transient_db_error`. Pool checkout timeouts
    and query-level errors are not retried.
    """
    return retry_async(
        policy=policy, retry_on=is_transient_db_error, operation=operation
    )
