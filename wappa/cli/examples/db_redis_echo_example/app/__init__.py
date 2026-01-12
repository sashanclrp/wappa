"""
DB + Redis Echo Example

Demonstrates PostgresDatabasePlugin with Redis caching for conversation management.

Architecture:
- Redis: Active conversation caching (fast access)
- PostgreSQL: Long-term message persistence (Supabase)
- Echo bot: Message tracking with history and close commands

SOLID Architecture:
- handlers/: Command and message handling (SRP)
- models/: Cache and database models (SRP)
- utils/: Extraction, cache, and database utilities (SRP)
- master_event.py: Thin orchestration layer (~200-300 lines)
"""

from .master_event import DBRedisExampleHandler

__all__ = ["DBRedisExampleHandler"]
