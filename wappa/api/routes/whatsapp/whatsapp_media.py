"""WhatsApp media messaging API endpoints.

Provides REST API endpoints for WhatsApp media operations:
- POST /api/whatsapp/media/upload: Upload media files
- POST /api/whatsapp/media/send-image: Send image messages
- POST /api/whatsapp/media/send-video: Send video messages
- POST /api/whatsapp/media/send-audio: Send audio messages
- POST /api/whatsapp/media/send-document: Send document messages
- POST /api/whatsapp/media/send-sticker: Send sticker messages
- GET /api/whatsapp/media/info/{media_id}: Get media information
- GET /api/whatsapp/media/download/{media_id}: Download media
- DELETE /api/whatsapp/media/{media_id}: Delete media

Router configuration:
- Prefix: /media
- Tags: ["WhatsApp - Media"]
- Full URL: /api/whatsapp/media/
"""

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from wappa.api.dependencies.event_dependencies import get_api_event_dispatcher
from wappa.api.dependencies.inbox_context import (
    get_inbox_messenger,
    requires_capability,
)
from wappa.api.dependencies.media_transfer import (
    LibraryMediaUploader,
    get_media_uploader,
)
from wappa.api.dependencies.whatsapp_dependencies import get_whatsapp_media_payloads
from wappa.api.routes.whatsapp.route_families import RouteFamily
from wappa.api.utils import direct_target, dispatch_message_event, map_send_errors
from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.domain.interfaces.conversation_capabilities import ReadOutcome
from wappa.domain.interfaces.media_library import IMediaLibrary
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.models.media_result import (
    MediaDeleteResult,
    MediaInfoResult,
    MediaUploadResult,
)
from wappa.domain.results import MessageResult, OperationOutcome
from wappa.messaging.whatsapp.models.media_models import (
    AudioMessage,
    DocumentMessage,
    ImageMessage,
    StickerMessage,
    VideoMessage,
)
from wappa.messaging.whatsapp.payload_builders import WhatsAppMediaPayloadBuilder

# One prefix, four capability groups. `DELETE /media/{id}` destroys a platform
# asset, so it is gated apart from the reads it sits next to — see ADR-0009.
_family = RouteFamily(
    prefix="/media",
    tags=["WhatsApp - Media"],
    responses={
        400: {"description": "Bad Request - Invalid media format or size"},
        401: {"description": "Unauthorized - Invalid inbox credentials"},
        404: {"description": "Not Found - Media not found"},
        413: {"description": "Payload Too Large - Media file too large"},
        415: {"description": "Unsupported Media Type - Invalid file type"},
        429: {"description": "Rate Limited - Too many requests"},
        500: {"description": "Internal Server Error"},
    },
)
send_router = _family.router()  # sends media to a User
upload_router = _family.router()  # creates a platform media asset
management_router = _family.router()  # destroys a platform media asset
router = _family.router()  # reads: download, info, limits


@upload_router.post(
    "/upload",
    response_model=MediaUploadResult,
    summary="Upload Media",
    description=(
        "Upload a media file through the Inbox's IMediaLibrary and get a media "
        "ID for sending. WhatsApp: Media API (`media_type` honoured). Instagram: "
        "`message_attachments` (image png/jpeg/gif, audio, video, pdf). A "
        "Platform without a media library answers 501."
    ),
)
@map_send_errors("upload media")
async def upload_media(
    file: UploadFile = File(..., description="Media file to upload"),
    media_type: str | None = Form(
        None, description="MIME type (auto-detected if not provided)"
    ),
    media_handler: LibraryMediaUploader = Depends(get_media_uploader),
) -> MediaUploadResult:
    """Upload media for the selected Inbox (any Platform with a media library).

    A failed result answers its mapped status: 415 for an unsupported MIME
    type, 413 for an oversize file, 400 otherwise.
    """
    content_type = media_type or file.content_type
    if not content_type:
        raise HTTPException(
            status_code=400,
            detail="Could not determine media type. Please provide media_type parameter.",
        )
    return await media_handler.upload_media_from_bytes(
        file_data=await file.read(),
        media_type=content_type,
        filename=file.filename or "uploaded_file",
    )


@send_router.post(
    "/send-image",
    response_model=MessageResult,
    summary="Send Image Message",
    description="Send an image message with optional caption and reply context",
)
@map_send_errors("send image")
@dispatch_message_event()
async def send_image_message(
    request: ImageMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send image message via WhatsApp.

    Supports JPEG and PNG images up to 5MB with optional captions.
    """
    return await messenger.send_image(
        image_source=request.media_source,
        target=direct_target(messenger, request),
        caption=request.caption,
        reply_to_message_id=request.reply_to_message_id,
    )


@send_router.post(
    "/send-video",
    response_model=MessageResult,
    summary="Send Video Message",
    description="Send a video message with optional caption and reply context",
)
@map_send_errors("send video")
@dispatch_message_event()
async def send_video_message(
    request: VideoMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send video message via WhatsApp.

    Supports MP4 and 3GP videos up to 16MB with optional captions.
    """
    return await messenger.send_video(
        video_source=request.media_source,
        target=direct_target(messenger, request),
        caption=request.caption,
        reply_to_message_id=request.reply_to_message_id,
        transcript=request.transcript,
    )


@send_router.post(
    "/send-audio",
    response_model=MessageResult,
    summary="Send Audio Message",
    description=(
        "Send an audio message. Formats per Platform: WhatsApp .aac/.amr/.mp3/"
        ".m4a/.ogg (16 MB), voice note (is_voice) .ogg Opus mono only; "
        "Instagram .aac/.m4a/.wav/.mp4 (25 MB). A wrong format answers 400."
    ),
)
@map_send_errors("send audio")
@dispatch_message_event()
async def send_audio_message(
    request: AudioMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send audio on the path Platform; audio has no caption."""
    return await messenger.send_audio(
        audio_source=request.media_source,
        target=direct_target(messenger, request),
        reply_to_message_id=request.reply_to_message_id,
        transcript=request.transcript,
        is_voice=request.is_voice,
    )


@send_router.post(
    "/send-document",
    response_model=MessageResult,
    summary="Send Document Message",
    description="Send a document message with optional caption, filename and reply context",
)
@map_send_errors("send document")
@dispatch_message_event()
async def send_document_message(
    request: DocumentMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send document message via WhatsApp.

    Supports TXT, PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX up to 100MB.
    """
    return await messenger.send_document(
        document_source=request.media_source,
        target=direct_target(messenger, request),
        filename=request.filename,
        caption=request.caption,
        reply_to_message_id=request.reply_to_message_id,
    )


@send_router.post(
    "/send-sticker",
    response_model=MessageResult,
    summary="Send Sticker Message",
    description=(
        "Send a WhatsApp sticker. Format: WebP only (image/webp; 512x512, up to "
        "100 KB static or 500 KB animated). `media_source` is a `.webp` URL, a "
        "`.webp` file path or an uploaded media ID; any other extension is "
        "rejected with 400 before Meta is called."
    ),
)
@map_send_errors("send sticker")
@dispatch_message_event()
async def send_sticker_message(
    request: StickerMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send sticker message via WhatsApp.

    WhatsApp stickers are WebP only (512x512; 100 KB static, 500 KB animated).
    A non-WebP source is a 400 here: Meta would accept a PNG link and only
    fail later with status 131053. Stickers do not support captions.
    """
    return await messenger.send_sticker(
        sticker_source=request.media_source,
        target=direct_target(messenger, request),
        reply_to_message_id=request.reply_to_message_id,
    )


_READ_STATUS = {
    ReadOutcome.NOT_FOUND: 404,
    ReadOutcome.ACCESS_DENIED: 403,
    ReadOutcome.REJECTED: 400,
    ReadOutcome.UNAVAILABLE: 503,
}
_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "video/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "application/pdf": ".pdf",
}


@router.get(
    "/info/{media_id}",
    response_model=MediaInfoResult,
    summary="Get Media Information",
    description=(
        "Describe a stored media file through the Inbox's IMediaLibrary: URL "
        "(WhatsApp: valid about 5 minutes), MIME type, size and SHA-256. A "
        "Platform without a media info endpoint (Instagram) answers 501."
    ),
)
@map_send_errors("get media info")
async def get_media_info(
    media_id: str,
    library: IMediaLibrary = Depends(requires_capability(IMediaLibrary)),
    messenger: IMessenger = Depends(get_inbox_messenger),
) -> MediaInfoResult:
    result = await library.info(media_id)
    if not result.found or result.value is None:
        raise HTTPException(
            status_code=_READ_STATUS.get(result.outcome, 502),
            detail=result.error or result.outcome.value,
        )
    info = result.value
    return MediaInfoResult(
        success=True,
        platform=messenger.platform,
        media_id=info.media_id,
        url=info.url,
        mime_type=info.mime_type,
        file_size=info.size,
        sha256=info.sha256,
        inbox_id=messenger.inbox_id,
    )


@router.get(
    "/download/{media_id:path}",
    summary="Download Media",
    description=(
        "Download inbound media through the Inbox's IMediaLibrary. Pass the "
        "webhook's `media_id` unchanged, URL-encoded: a Media ID on WhatsApp, "
        "the attachment URL on Instagram (fetched without credentials from Meta "
        "CDN hosts). A Platform without a media library answers 501."
    ),
)
async def download_media(
    media_id: str,
    library: IMediaLibrary = Depends(requires_capability(IMediaLibrary)),
) -> Response:
    """Download media by ID; ``Content-Type`` comes from ``MediaBytes``."""
    result = await library.download(media_id)
    if not result.found or result.value is None:
        status = 413 if result.error_code == "SIZE" else None
        raise HTTPException(
            status_code=status or _READ_STATUS.get(result.outcome, 502),
            detail=result.error or result.outcome.value,
        )
    media = result.value
    stem = "media" if "://" in media_id else f"media_{media_id}"
    filename = stem + _EXTENSIONS.get(media.content_type or "", "")
    return Response(
        content=media.content,
        media_type=media.content_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


_DELETE_STATUS = {"HTTP_400": 404, "HTTP_404": 404, "HTTP_401": 403, "HTTP_403": 403}


@management_router.delete(
    "/{media_id}",
    response_model=MediaDeleteResult,
    summary="Delete Media",
    description=(
        "Delete a stored media file through the Inbox's IMediaLibrary "
        "(WhatsApp media persist 30 days unless deleted earlier). A Platform "
        "without a media delete endpoint (Instagram) answers 501."
    ),
)
@map_send_errors("delete media")
async def delete_media(
    media_id: str,
    library: IMediaLibrary = Depends(requires_capability(IMediaLibrary)),
) -> MediaDeleteResult:
    result = await library.delete(media_id)
    if not result.success:
        status = 502 if result.outcome is OperationOutcome.INDETERMINATE else 400
        raise HTTPException(
            status_code=_DELETE_STATUS.get(result.error_code or "", status),
            detail=result.error or result.outcome.value,
        )
    return MediaDeleteResult(
        success=True,
        platform=result.platform,
        media_id=result.media_id,
        inbox_id=result.inbox_id,
    )


@router.get(
    "/limits",
    summary="Get Media Limits",
    description="Get platform-specific media limits and supported types",
)
async def get_media_limits(
    payloads: WhatsAppMediaPayloadBuilder = Depends(get_whatsapp_media_payloads),
) -> dict:
    """Get WhatsApp media limits and constraints.

    Returns supported MIME types, file size limits, and platform constraints.
    """
    return payloads.get_media_limits()
