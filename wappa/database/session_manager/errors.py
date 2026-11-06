"""Errors raised by the PostgreSQL session manager."""

from __future__ import annotations


class TransientDatabaseError(Exception):
    """Database error that may be retried (connection timeouts, network issues)."""
