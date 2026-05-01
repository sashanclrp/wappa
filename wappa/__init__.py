"""
Wappa - Open Source WhatsApp Business Framework

A clean, modern Python library for building WhatsApp Business applications
with minimal setup and maximum flexibility.

Clean Import Interface (SRP Compliance):
- Only framework essentials exposed at top level
- Domain-specific imports available via wappa.domain paths
- Follows Clean Architecture principles
"""

# Framework Essentials Only (SRP: Framework Foundation)
# Dynamic version from pyproject.toml
from .core.config.settings import settings
from .core.context import WappaContext
from .core.events.event_handler import WappaEventHandler
from .core.expiry import expiry_registry
from .core.factory import WappaBuilder, WappaPlugin
from .core.plugins import ExpiryPlugin
from .core.wappa_app import Wappa
from .domain.events.cron_event import CronEvent
from .domain.events.external_event import ExternalEvent
from .domain.interfaces.webhook_processor import IWebhookProcessor
from .webhooks.core.webhook_interfaces import CustomWebhook

__version__ = settings.version

__all__ = [
    # Core Framework Components
    "Wappa",
    "WappaEventHandler",
    "WappaBuilder",
    "WappaPlugin",
    # Custom Webhook Field Registry
    "CustomWebhook",
    # External Webhook Gateway
    "ExternalEvent",
    "IWebhookProcessor",
    "WappaContext",
    # Cron Scheduling
    "CronEvent",
    # Expiry Actions System
    "expiry_registry",
    "ExpiryPlugin",
]
