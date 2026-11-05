"""API routes module for Wappa framework."""

from .health import router as health_router
from .whatsapp_combined import create_messaging_router

__all__ = ["create_messaging_router", "health_router"]
