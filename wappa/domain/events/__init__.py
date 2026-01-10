"""
Domain events module.

Provides event models for different contexts:
- APIMessageEvent: Events for API-sent messages (outgoing)
- Webhook events are defined in wappa.webhooks module (incoming)
"""

from .api_message_event import APIMessageEvent

__all__ = ["APIMessageEvent"]
