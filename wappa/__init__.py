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
from .core.wappa_app import Wappa
from .core.events.event_handler import WappaEventHandler
from .core.factory import WappaBuilder, WappaPlugin

# Dynamic version from pyproject.toml
from .core.config.settings import settings

__version__ = settings.version

__all__ = [
    # Core Framework Components
    "Wappa",
    "WappaEventHandler", 
    "WappaBuilder",
    "WappaPlugin",
]
