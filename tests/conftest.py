"""
Pytest configuration and common fixtures for Wappa tests.

Provides shared fixtures and configuration for all test modules.
"""

import asyncio
import os
import tempfile
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Test database setup
TEST_DB_URL = "sqlite+aiosqlite:///./test_wappa.db"
TEST_REDIS_URL = "redis://localhost:6379/15"  # Use DB 15 for tests


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db() -> Generator[str, None, None]:
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db_url = f"sqlite+aiosqlite:///{db_path}"
    yield db_url

    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    mock = MagicMock()
    mock.ping = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_auth_middleware():
    """Mock authentication middleware for testing."""

    class MockAuthMiddleware:
        def __init__(self, app, **kwargs):
            self.app = app
            self.kwargs = kwargs

        async def __call__(self, scope, receive, send):
            # Just pass through for testing
            await self.app(scope, receive, send)

    return MockAuthMiddleware


@pytest.fixture
def mock_rate_limit_middleware():
    """Mock rate limiting middleware for testing."""

    class MockRateLimitMiddleware:
        def __init__(self, app, **kwargs):
            self.app = app
            self.kwargs = kwargs

        async def __call__(self, scope, receive, send):
            # Just pass through for testing
            await self.app(scope, receive, send)

    return MockRateLimitMiddleware


@pytest.fixture
def basic_fastapi_app() -> FastAPI:
    """Create a basic FastAPI app for testing."""
    app = FastAPI(title="Test App")

    @app.get("/test")
    async def test_endpoint():
        return {"message": "test"}

    return app


@pytest.fixture
def test_client(basic_fastapi_app: FastAPI) -> TestClient:
    """Create a test client for FastAPI app."""
    return TestClient(basic_fastapi_app)


# Environment setup for tests
@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Set up test environment variables."""
    # Override environment for tests
    monkeypatch.setenv("WAPPA_ENVIRONMENT", "test")
    monkeypatch.setenv("WAPPA_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("WP_PHONE_ID", "test_phone_id")
    monkeypatch.setenv("WP_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("WP_WEBHOOK_TOKEN", "test_webhook_token")
