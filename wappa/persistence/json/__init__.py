"""
JSON-based cache implementation for Wappa framework.

Provides persistent cache storage using JSON files on disk.
Suitable for development, debugging, and single-process deployments.

Usage:
    wappa = Wappa(cache="json")
    # Cache files will be created in {project_root}/cache/
"""

from .json_cache_factory import JSONCacheFactory

__all__ = ["JSONCacheFactory"]
