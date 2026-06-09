"""Local route-level rate limiting for Wappa applications."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from math import ceil
from typing import TYPE_CHECKING, Literal

from fastapi import HTTPException, Request

from ...core.logging.logger import get_app_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ...core.factory.wappa_builder import WappaBuilder

RateLimitKeyBy = Literal["client_ip", "inbox_id", "inbox_id_and_client_ip"]


@dataclass(frozen=True, slots=True)
class RateLimitProfile:
    """Named local rate-limit policy for route dependencies."""

    name: str
    limit: int
    window_seconds: int
    key_by: RateLimitKeyBy = "client_ip"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("rate limit profile name must be a non-empty string")
        if self.limit < 1:
            raise ValueError("rate limit profile limit must be >= 1")
        if self.window_seconds < 1:
            raise ValueError("rate limit profile window_seconds must be >= 1")


class LocalRateLimiter:
    """Per-process fixed-window limiter stored on ``app.state``."""

    def __init__(self, profiles: list[RateLimitProfile]) -> None:
        self._profiles = {profile.name: profile for profile in profiles}
        if len(self._profiles) != len(profiles):
            raise ValueError("rate limit profile names must be unique")
        self._windows: dict[tuple[str, str], tuple[float, int]] = {}

    def check(self, profile_name: str, request: Request) -> int | None:
        profile = self._profiles.get(profile_name)
        if profile is None:
            raise RuntimeError(f"Unknown rate limit profile: {profile_name}")

        now = time.monotonic()
        key = (profile.name, self._derive_key(profile, request))
        window_start, count = self._windows.get(key, (now, 0))
        elapsed = now - window_start
        if elapsed >= profile.window_seconds:
            window_start = now
            count = 0

        if count >= profile.limit:
            retry_after = max(1, ceil(profile.window_seconds - elapsed))
            return retry_after

        self._windows[key] = (window_start, count + 1)
        return None

    def _derive_key(self, profile: RateLimitProfile, request: Request) -> str:
        client_ip = request.client.host if request.client else "unknown"

        if profile.key_by == "client_ip":
            return client_ip

        inbox_id = self._require_inbox_id(profile, request)
        if profile.key_by == "inbox_id":
            return inbox_id

        return f"{inbox_id}:{client_ip}"

    @staticmethod
    def _require_inbox_id(profile: RateLimitProfile, request: Request) -> str:
        inbox_id = request.path_params.get("inbox_id")
        if not isinstance(inbox_id, str) or not inbox_id:
            raise RuntimeError(
                f"Rate limit profile {profile.name!r} requires route inbox_id"
            )
        return inbox_id


class RateLimitPlugin:
    """Registers local rate-limit profiles on FastAPI application state."""

    def __init__(self, profiles: list[RateLimitProfile]) -> None:
        if not profiles:
            raise ValueError("RateLimitPlugin requires at least one profile")
        self.profiles = profiles

    def configure(self, builder: WappaBuilder) -> None:
        builder.add_startup_hook(self.startup, priority=30)
        builder.add_shutdown_hook(self.shutdown, priority=30)

    async def startup(self, app: FastAPI) -> None:
        app.state.wappa_rate_limiter = LocalRateLimiter(self.profiles)
        get_app_logger().debug(
            "RateLimitPlugin registered %s local profile(s)", len(self.profiles)
        )

    async def shutdown(self, app: FastAPI) -> None:
        if hasattr(app.state, "wappa_rate_limiter"):
            delattr(app.state, "wappa_rate_limiter")


def rate_limit(profile_name: str) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency factory for a named local rate-limit profile."""

    async def dependency(request: Request) -> None:
        limiter = getattr(request.app.state, "wappa_rate_limiter", None)
        if not isinstance(limiter, LocalRateLimiter):
            raise RuntimeError("RateLimitPlugin is not configured")

        retry_after = limiter.check(profile_name, request)
        if retry_after is None:
            return

        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    return dependency
