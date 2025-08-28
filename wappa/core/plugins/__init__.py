"""
Wappa Core Plugins Module

This module contains all the core plugins that extend Wappa functionality:
- WappaCorePlugin: Essential Wappa framework functionality (logging, middleware, routes)
- Database plugins for SQLModel/SQLAlchemy integration
- Redis plugin for caching and session management
- Middleware plugins (CORS, Auth, Rate Limiting)
- Webhook plugins for payment providers and custom endpoints
"""

from .auth_plugin import AuthPlugin
from .cors_plugin import CORSPlugin
from .custom_middleware_plugin import CustomMiddlewarePlugin
from .database_plugin import DatabasePlugin
from .rate_limit_plugin import RateLimitPlugin
from .redis_plugin import RedisPlugin
from .wappa_core_plugin import WappaCorePlugin
from .webhook_plugin import WebhookPlugin

__all__ = [
    # Core Framework
    "WappaCorePlugin",
    # Core Infrastructure
    "DatabasePlugin",
    "RedisPlugin",
    # Middleware
    "CORSPlugin",
    "AuthPlugin",
    "RateLimitPlugin",
    "CustomMiddlewarePlugin",
    # Integrations
    "WebhookPlugin",
]
