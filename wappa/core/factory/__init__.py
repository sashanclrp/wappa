"""
Wappa Factory Module

This module provides the plugin-based factory system for building extensible
Wappa applications. It includes the WappaBuilder class and plugin interfaces
that allow users to extend FastAPI functionality without modifying core code.
"""

from .plugin import WappaPlugin
from .wappa_builder import WappaBuilder

__all__ = [
    "WappaBuilder",
    "WappaPlugin",
]
