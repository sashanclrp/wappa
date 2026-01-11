"""
Wappa ExpiryActions System

Provides time-based automation with decorator-based handler registration
and Redis KEYSPACE notification-driven execution.

Example:
    from wappa import expiry_registry

    @expiry_registry.on_expire_action("payment_reminder")
    async def handle_payment_reminder(identifier: str, full_key: str):
        print(f"Payment reminder for transaction {identifier}")
        # Business logic here

Components:
    - ExpirationHandlerRegistry: Decorator-based handler registration
    - run_expiry_listener: Background task for Redis expiry events
    - AppContext: Dependency injection container for FastAPI app
    - RedisConnectionManager: Redis connection lifecycle
    - ExpiryEventParser: Key parsing and handler resolution
    - ExpiryDispatcher: Async handler dispatch
    - ReconnectionStrategy: Exponential backoff reconnection
    - Context Helpers: Utility functions for messenger and cache bootstrapping
"""

# Core listener function
# Context management (Issue 1 fix)
from .app_context import AppContext, get_app_context

# Connection management (Issue 2 fix - extracted class)
from .connection import ConnectionConfig, RedisConnection, RedisConnectionManager

# Context helpers for expiry handlers
from .context_helpers import (
    CacheFactoryCreationError,
    ExpiryContextError,
    FastAPIAppNotAvailableError,
    HTTPSessionNotAvailableError,
    MessengerCreationError,
    create_expiry_cache_factory,
    create_expiry_messenger,
    parse_tenant_from_expired_key,
)

# Handler dispatch (Issue 2 fix - extracted class)
from .dispatcher import ExpiryDispatcher
from .listener import get_fastapi_app, run_expiry_listener, set_fastapi_app

# Event parsing (Issue 2 & 3 fix - extracted class, uses registry.resolve)
from .parser import ExpiryEvent, ExpiryEventParser

# Reconnection strategy (Issue 2 fix - extracted class)
from .reconnection import ReconnectionConfig, ReconnectionStrategy

# Registry and handler types
from .registry import AsyncHandler, ExpirationHandlerRegistry, expiry_registry

__all__ = [
    # Primary exports (backward compatible)
    "ExpirationHandlerRegistry",
    "expiry_registry",
    "AsyncHandler",
    "run_expiry_listener",
    "get_fastapi_app",
    "set_fastapi_app",
    # Context management
    "AppContext",
    "get_app_context",
    # Connection components
    "RedisConnectionManager",
    "RedisConnection",
    "ConnectionConfig",
    # Event components
    "ExpiryEventParser",
    "ExpiryEvent",
    # Dispatch components
    "ExpiryDispatcher",
    # Reconnection components
    "ReconnectionStrategy",
    "ReconnectionConfig",
    # Context helpers for expiry handlers
    "create_expiry_messenger",
    "create_expiry_cache_factory",
    "parse_tenant_from_expired_key",
    # Context helper exceptions
    "ExpiryContextError",
    "FastAPIAppNotAvailableError",
    "HTTPSessionNotAvailableError",
    "MessengerCreationError",
    "CacheFactoryCreationError",
]
