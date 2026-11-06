"""WhatsApp Cloud API limits under ``/api/whatsapp``.

- ``GET /messages/limits``: text message limits
- ``GET /media/limits``: media MIME types, sizes, caption and filename support

The interactive limits are shared by every Platform and stay on the shared
router (``GET /api/{platform}/interactive/limits``); Template limits live with
Template info.
"""

from fastapi import APIRouter, Depends

from wappa.api.dependencies.whatsapp_dependencies import (
    get_whatsapp_media_payloads,
    get_whatsapp_message_payloads,
)
from wappa.messaging.whatsapp.payload_builders import (
    WhatsAppMediaPayloadBuilder,
    WhatsAppMessagePayloadBuilder,
)

router = APIRouter(tags=["WhatsApp - Limits"])


@router.get(
    "/messages/limits",
    summary="Get Text Message Limits",
    description="WhatsApp text message limits.",
)
async def get_message_limits(
    payloads: WhatsAppMessagePayloadBuilder = Depends(get_whatsapp_message_payloads),
) -> dict:
    return payloads.get_message_limits()


@router.get(
    "/media/limits",
    summary="Get Media Limits",
    description="WhatsApp media limits and supported MIME types.",
)
async def get_media_limits(
    payloads: WhatsAppMediaPayloadBuilder = Depends(get_whatsapp_media_payloads),
) -> dict:
    return payloads.get_media_limits()
