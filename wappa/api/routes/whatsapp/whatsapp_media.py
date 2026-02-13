"""
WhatsApp media messaging API endpoints.

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
- Prefix: /whatsapp/media
- Tags: ["WhatsApp - Media"]
- Full URL: /api/whatsapp/media/ (when included with /api prefix)
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from wappa.api.dependencies.event_dependencies import get_api_event_dispatcher
from wappa.api.dependencies.whatsapp_dependencies import (
    get_whatsapp_media_handler,
    get_whatsapp_messenger,
)
from wappa.api.dependencies.whatsapp_media_dependencies import (
    get_whatsapp_media_factory,
)
from wappa.api.utils import dispatch_message_event
from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.domain.factories.media_factory import MediaFactory
from wappa.domain.interfaces.media_interface import IMediaHandler
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.models.media_result import (
    MediaDeleteResult,
    MediaInfoResult,
    MediaUploadResult,
)
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.media_models import (
    AudioMessage,
    DocumentMessage,
    ImageMessage,
    StickerMessage,
    VideoMessage,
)

# Create router with WhatsApp Media configuration
router = APIRouter(
    prefix="/whatsapp/media",
    tags=["WhatsApp - Media"],
    responses={
        400: {"description": "Bad Request - Invalid media format or size"},
        401: {"description": "Unauthorized - Invalid tenant credentials"},
        404: {"description": "Not Found - Media not found"},
        413: {"description": "Payload Too Large - Media file too large"},
        415: {"description": "Unsupported Media Type - Invalid file type"},
        429: {"description": "Rate Limited - Too many requests"},
        500: {"description": "Internal Server Error"},
    },
)


@router.post(
    "/upload",
    response_model=MediaUploadResult,
    summary="Upload Media",
    description="Upload a media file to WhatsApp servers and get media ID for sending",
)
async def upload_media(
    file: UploadFile = File(..., description="Media file to upload"),
    media_type: str | None = Form(
        None, description="MIME type (auto-detected if not provided)"
    ),
    media_handler: IMediaHandler = Depends(get_whatsapp_media_handler),
) -> MediaUploadResult:
    """Upload media file to WhatsApp servers.

    Based on existing WhatsAppServiceMedia.upload_media() functionality.
    Supports all WhatsApp media types with proper validation.
    """
    try:
        # Read file data
        file_data = await file.read()

        # Use provided MIME type or file's content type
        content_type = media_type or file.content_type

        if not content_type:
            raise HTTPException(
                status_code=400,
                detail="Could not determine media type. Please provide media_type parameter.",
            )

        # Upload using media handler
        result = await media_handler.upload_media_from_bytes(
            file_data=file_data,
            media_type=content_type,
            filename=file.filename or "uploaded_file",
        )

        if not result.success:
            if result.error_code == "MIME_TYPE_UNSUPPORTED":
                raise HTTPException(status_code=415, detail=result.error)
            elif result.error_code == "FILE_SIZE_EXCEEDED":
                raise HTTPException(status_code=413, detail=result.error)
            else:
                raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}") from e


@router.post(
    "/send-image",
    response_model=MessageResult,
    summary="Send Image Message",
    description="Send an image message with optional caption and reply context",
)
@dispatch_message_event("image")
async def send_image_message(
    request: ImageMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send image message via WhatsApp.

    Supports JPEG and PNG images up to 5MB with optional captions.
    """
    try:
        result = await messenger.send_image(
            image_source=request.media_source,
            recipient=request.recipient,
            caption=request.caption,
            reply_to_message_id=request.reply_to_message_id,
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send image: {str(e)}"
        ) from e


@router.post(
    "/send-video",
    response_model=MessageResult,
    summary="Send Video Message",
    description="Send a video message with optional caption and reply context",
)
@dispatch_message_event("video")
async def send_video_message(
    request: VideoMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send video message via WhatsApp.

    Supports MP4 and 3GP videos up to 16MB with optional captions.
    """
    try:
        result = await messenger.send_video(
            video_source=request.media_source,
            recipient=request.recipient,
            caption=request.caption,
            reply_to_message_id=request.reply_to_message_id,
            transcript=request.transcript,
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send video: {str(e)}"
        ) from e


@router.post(
    "/send-audio",
    response_model=MessageResult,
    summary="Send Audio Message",
    description="Send an audio message with optional reply context",
)
@dispatch_message_event("audio")
async def send_audio_message(
    request: AudioMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send audio message via WhatsApp.

    Supports AAC, AMR, MP3, M4A, and OGG audio up to 16MB.
    Note: Audio messages do not support captions.
    """
    try:
        result = await messenger.send_audio(
            audio_source=request.media_source,
            recipient=request.recipient,
            reply_to_message_id=request.reply_to_message_id,
            transcript=request.transcript,
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send audio: {str(e)}"
        ) from e


@router.post(
    "/send-document",
    response_model=MessageResult,
    summary="Send Document Message",
    description="Send a document message with optional filename and reply context",
)
@dispatch_message_event("document")
async def send_document_message(
    request: DocumentMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send document message via WhatsApp.

    Supports TXT, PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX up to 100MB.
    """
    try:
        result = await messenger.send_document(
            document_source=request.media_source,
            recipient=request.recipient,
            filename=request.filename,
            caption=request.caption,
            reply_to_message_id=request.reply_to_message_id,
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send document: {str(e)}"
        ) from e


@router.post(
    "/send-sticker",
    response_model=MessageResult,
    summary="Send Sticker Message",
    description="Send a sticker message with optional reply context",
)
@dispatch_message_event("sticker")
async def send_sticker_message(
    request: StickerMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send sticker message via WhatsApp.

    Supports WebP images only (100KB static, 500KB animated).
    Note: Sticker messages do not support captions.
    """
    try:
        result = await messenger.send_sticker(
            sticker_source=request.media_source,
            recipient=request.recipient,
            reply_to_message_id=request.reply_to_message_id,
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send sticker: {str(e)}"
        ) from e


@router.get(
    "/info/{media_id}",
    response_model=MediaInfoResult,
    summary="Get Media Information",
    description="Retrieve media information including URL, MIME type, and file size",
)
async def get_media_info(
    media_id: str, media_handler: IMediaHandler = Depends(get_whatsapp_media_handler)
) -> MediaInfoResult:
    """Get media information by ID.

    Returns media URL (valid for 5 minutes), MIME type, file size, and SHA256 hash.
    """
    try:
        result = await media_handler.get_media_info(media_id)

        if not result.success:
            if "not found" in result.error.lower():
                raise HTTPException(status_code=404, detail=result.error)
            else:
                raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get media info: {str(e)}"
        ) from e


@router.get(
    "/download/{media_id}",
    summary="Download Media",
    description="Download media file by ID as streaming response",
)
async def download_media(
    media_id: str, media_handler: IMediaHandler = Depends(get_whatsapp_media_handler)
):
    """Download media by ID as streaming response.

    Returns media file as streaming download with appropriate headers.
    """
    try:
        # Get media info first for headers
        info_result = await media_handler.get_media_info(media_id)
        if not info_result.success:
            if "not found" in info_result.error.lower():
                raise HTTPException(status_code=404, detail=info_result.error)
            else:
                raise HTTPException(status_code=400, detail=info_result.error)

        # Download media
        download_result = await media_handler.download_media(media_id)
        if not download_result.success:
            raise HTTPException(status_code=400, detail=download_result.error)

        # Create streaming response
        def generate_content():
            yield download_result.file_data

        # Determine filename
        filename = f"media_{media_id}"
        if download_result.mime_type:
            # Simple extension mapping
            ext_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "video/mp4": ".mp4",
                "audio/mpeg": ".mp3",
                "application/pdf": ".pdf",
            }
            if download_result.mime_type in ext_map:
                filename += ext_map[download_result.mime_type]

        return StreamingResponse(
            generate_content(),
            media_type=download_result.mime_type or "application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Length": str(download_result.file_size)
                if download_result.file_size
                else "",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to download media: {str(e)}"
        ) from e


@router.delete(
    "/{media_id}",
    response_model=MediaDeleteResult,
    summary="Delete Media",
    description="Delete media from WhatsApp servers",
)
async def delete_media(
    media_id: str, media_handler: IMediaHandler = Depends(get_whatsapp_media_handler)
) -> MediaDeleteResult:
    """Delete media by ID.

    Permanently removes media from WhatsApp servers.
    Media files persist for 30 days unless deleted earlier.
    """
    try:
        result = await media_handler.delete_media(media_id)

        if not result.success:
            if "not found" in result.error.lower():
                raise HTTPException(status_code=404, detail=result.error)
            else:
                raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete media: {str(e)}"
        ) from e


@router.get(
    "/limits",
    summary="Get Media Limits",
    description="Get platform-specific media limits and supported types",
)
async def get_media_limits(
    media_factory: MediaFactory = Depends(get_whatsapp_media_factory),
) -> dict:
    """Get WhatsApp media limits and constraints.

    Returns supported MIME types, file size limits, and platform constraints.
    """
    return media_factory.get_media_limits()
