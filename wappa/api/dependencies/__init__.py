"""
FastAPI dependency injection for the Wappa WhatsApp Framework.

Provides reusable dependencies for controllers, services, and middleware
following clean architecture patterns.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request

# Import existing dependencies
from .whatsapp_dependencies import *
from .whatsapp_media_dependencies import *
