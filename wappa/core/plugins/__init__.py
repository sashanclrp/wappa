"""
Wappa Core Plugins Module

This module contains all the core plugins that extend Wappa functionality:
- WappaCorePlugin: Essential Wappa framework functionality (logging, middleware, routes)
- PostgresDatabasePlugin for SQLModel/SQLAlchemy integration
- Redis plugin for caching and session management
- SSEEventsPlugin for native FastAPI SSE event streaming
- ExpiryPlugin: Redis expiry action listener for time-based automation
- Middleware plugins (CORS, Auth, Rate Limiting)
- Webhook plugins for payment providers and custom endpoints
"""

from ..auth import (
    AuthResult,
    AuthStrategy,
    BasicAuthStrategy,
    BearerTokenStrategy,
    JWTStrategy,
)
from .auth_plugin import AuthPlugin
from .cors_plugin import CORSPlugin
from .custom_middleware_plugin import CustomMiddlewarePlugin
from .expiry_plugin import ExpiryPlugin
from .postgres_database_plugin import PostgresDatabasePlugin
from .rate_limit_plugin import RateLimitPlugin
from .redis_plugin import RedisPlugin
from .redis_pubsub_plugin import RedisPubSubPlugin
from .sse_events_plugin import SSEEventsPlugin
from .wappa_core_plugin import WappaCorePlugin
from .webhook_plugin import WebhookPlugin

__all__ = [
    # Core Framework
    "WappaCorePlugin",
    # Core Infrastructure - Database
    "PostgresDatabasePlugin",
    # Core Infrastructure - Redis
    "RedisPlugin",
    "RedisPubSubPlugin",
    "SSEEventsPlugin",
    "ExpiryPlugin",
    # Middleware
    "CORSPlugin",
    "AuthPlugin",
    "RateLimitPlugin",
    "CustomMiddlewarePlugin",
    # Auth strategies and contracts
    "AuthStrategy",
    "AuthResult",
    "BearerTokenStrategy",
    "BasicAuthStrategy",
    "JWTStrategy",
    # Integrations
    "WebhookPlugin",
]
