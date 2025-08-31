"""
Memory-based cache implementation for Wappa framework.

Provides high-speed in-memory cache storage with TTL support.
Suitable for development, testing, and single-process deployments.

Usage:
    wappa = Wappa(cache="memory")
    # Data will be stored in memory with automatic TTL cleanup
"""

from .memory_cache_factory import MemoryCacheFactory

__all__ = ["MemoryCacheFactory"]
