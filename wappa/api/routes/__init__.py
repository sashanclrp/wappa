"""API routes module for Wappa framework."""

from .health import router as health_router
from .whatsapp_combined import whatsapp_router

__all__ = ["health_router", "whatsapp_router"]
