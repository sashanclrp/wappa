"""API routes module for Wappa framework."""

from .health import router as health_router
from .whatsapp_combined import create_whatsapp_router

__all__ = ["create_whatsapp_router", "health_router"]
