"""Tests for JWTStrategy leeway configuration."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import jwt
import pytest

from wappa.core.auth.strategies.jwt_strategy import JWTStrategy

SECRET = "test-secret-key-for-jwt-leeway-32b!"


def _make_token(*, exp_offset: int = 300, nbf_offset: int = 0) -> str:
    now = int(time.time())
    payload = {
        "sub": "user123",
        "iat": now,
        "exp": now + exp_offset,
        "nbf": now + nbf_offset,
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def _request_with_token(token: str) -> MagicMock:
    request = MagicMock()
    request.headers = {"authorization": f"Bearer {token}"}
    return request


class TestJWTLeeway:
    @pytest.mark.asyncio
    async def test_default_zero_leeway_rejects_expired(self):
        strategy = JWTStrategy(secret=SECRET)
        token = _make_token(exp_offset=-10)
        result = await strategy.authenticate(_request_with_token(token))
        assert not result.authenticated
        assert "expired" in result.error.lower()

    @pytest.mark.asyncio
    async def test_configured_leeway_accepts_small_nbf_skew(self):
        strategy = JWTStrategy(secret=SECRET, leeway=10)
        token = _make_token(nbf_offset=5)
        result = await strategy.authenticate(_request_with_token(token))
        assert result.authenticated

    @pytest.mark.asyncio
    async def test_configured_leeway_accepts_recently_expired(self):
        strategy = JWTStrategy(secret=SECRET, leeway=30)
        token = _make_token(exp_offset=-5)
        result = await strategy.authenticate(_request_with_token(token))
        assert result.authenticated

    @pytest.mark.asyncio
    async def test_leeway_does_not_rescue_fully_expired(self):
        strategy = JWTStrategy(secret=SECRET, leeway=5)
        token = _make_token(exp_offset=-60)
        result = await strategy.authenticate(_request_with_token(token))
        assert not result.authenticated

    def test_negative_leeway_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            JWTStrategy(secret=SECRET, leeway=-1)

    def test_zero_leeway_default(self):
        strategy = JWTStrategy(secret=SECRET)
        assert strategy._leeway == 0

    def test_float_leeway_accepted(self):
        strategy = JWTStrategy(secret=SECRET, leeway=2.5)
        assert strategy._leeway == 2.5
