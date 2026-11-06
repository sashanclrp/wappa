"""Shared media routes under ``/api/{platform}/media``.

- ``POST /upload``: upload a file through the Inbox's ``IMediaLibrary``
- ``POST /send-image``, ``/send-video``, ``/send-audio``, ``/send-document``,
  ``/send-sticker``: send media by URL or Media ID
- ``GET /info/{media_id}``, ``GET /download/{media_id}``,
  ``DELETE /{media_id}``: ``IMediaLibrary`` reads and delete (501 where the
  Platform has no such endpoint)

WhatsApp's media limits are a WhatsApp extension route
(``GET /api/whatsapp/media/limits``).
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
from wappa.api.routes.families import RouteFamily
from wappa.api.utils import (
    direct_target,
    dispatch_message_event,
    map_send_errors,
    raise_if_rate_limited,
)
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
from wappa.schemas.requests.media_models import (
    AudioMessage,
    DocumentMessage,
    ImageMessage,
    StickerMessage,
    VideoMessage,
)

# One prefix, four capability groups. `DELETE /media/{id}` destroys a platform
# asset, so it is gated apart from the reads it sits next to — see ADR-0024.
_family = RouteFamily(
    prefix="/media",
    tags=["Media"],
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
router = _family.router()  # reads: download, info


@upload_router.post(
    "/upload",
    response_model=MediaUploadResult,
    summary="Upload Media",
    description=(
        "Upload a media file through the Inbox's IMediaLibrary and get a media "
        "ID for sending. WhatsApp: Media API (`media_type` honoured). Instagram: "
        "`message_attachments` (image png/jpeg/gif, audio, video, pdf; WebP works only by URL). A "
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
    """Send an image on the path Platform, with an optional caption.

    Formats and sizes are the Platform's own (WhatsApp JPEG/PNG up to 5 MB;
    Instagram PNG/JPEG/GIF up to 8 MB); a wrong local format answers 400.
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
    """Send a video on the path Platform, with an optional caption.

    Formats and sizes are the Platform's own (WhatsApp MP4/3GP up to 16 MB;
    Instagram MP4/OGG/AVI/MOV/WebM up to 25 MB, another format by URL shared
    as a link).
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
    """Send a document on the path Platform, with optional filename and caption.

    Formats and sizes are the Platform's own (WhatsApp TXT, PDF and Office
    files up to 100 MB; Instagram PDF up to 25 MB, another format by URL
    shared as a text with the file name and link: the file opens from it).
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
        "Send a sticker. WhatsApp: WebP only (image/webp; 512x512, up to "
        "100 KB static or 500 KB animated). Instagram has no stickers and sends "
        "it as a png/jpeg/gif image (or a WebP URL). `media_source` is a URL, a file path or an "
        "uploaded media ID; an extension the Platform does not take is "
        "rejected with 400 before the Platform is called."
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
    """Send a sticker on the path Platform; stickers take no caption.

    WhatsApp stickers are WebP only (512x512; 100 KB static, 500 KB animated):
    a non-WebP source is a 400 there, since Meta would accept a PNG link and
    only fail later with status 131053. Instagram sends the sticker as an image.
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
        raise_if_rate_limited(result.retry_after, result.error)
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
        raise_if_rate_limited(result.retry_after, result.error)
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
        raise_if_rate_limited(result.retry_after, result.error)
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
