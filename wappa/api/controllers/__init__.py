"""
API Controllers for Wappa framework.

Controllers handle business logic and coordinate between routes and services,
following clean architecture principles and single responsibility principle.
"""

from .webhook_controller import WebhookController

__all__ = ["WebhookController"]
