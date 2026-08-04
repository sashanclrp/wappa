from typing import cast

from openai import AsyncOpenAI

from wappa import WappaEventHandler
from wappa.core.config import settings
from wappa.core.logging import get_logger
from wappa.messaging.whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger
from wappa.webhooks import InboundMessageWebhook
from wappa.webhooks.whatsapp.message_types.audio import WhatsAppAudioMessage

from .openai_utils import AudioProcessingService

logger = get_logger("TranscriptEventHandler")


class TranscriptEventHandler(WappaEventHandler):
    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        message_type = webhook.get_message_type_name()
        messenger = cast(WhatsAppMessenger, self.messenger)

        await messenger.mark_as_read(webhook.message.message_id)

        if message_type == "audio":
            audio_message = cast(WhatsAppAudioMessage, webhook.message)
            audio_id = audio_message.audio.id

            openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
            audio_service = AudioProcessingService(openai_client)

            # Option 1: Using tempfile context manager (automatic cleanup)
            async with messenger.media_handler.download_media_tempfile(
                audio_id
            ) as audio_download:
                if audio_download.success:
                    assert audio_download.file_path is not None
                    transcription = await audio_service.transcribe_audio(
                        audio_download.file_path
                    )
                    await messenger.send_text(
                        f"*Transcript:*\n\n{transcription}", webhook.user.user_id
                    )
                    logger.info(
                        f"Transcribed audio from temp file: {audio_download.file_path}"
                    )
                else:
                    logger.error(f"Failed to download audio: {audio_download.error}")
                    await messenger.send_text(
                        "Sorry, I couldn't download the audio file.",
                        webhook.user.user_id,
                    )

            # Option 2: Memory-only processing (no files created)
            # Uncomment to use bytes-based processing instead:
            # audio_bytes_result = await self.messenger.media_handler.get_media_as_bytes(audio_id)
            # if audio_bytes_result.success:
            #     transcription = await audio_service.transcribe_audio(audio_bytes_result.file_data, "audio.ogg")
            #     await self.messenger.send_text(f"*Transcript:*\n\n{transcription}", webhook.user.user_id)
            #     logger.info(f"Transcribed audio from memory ({audio_bytes_result.file_size} bytes)")
            # else:
            #     logger.error(f"Failed to download audio: {audio_bytes_result.error}")
            #     await self.messenger.send_text("Sorry, I couldn't download the audio file.", webhook.user.user_id)
        else:
            await messenger.send_text(
                "*Hey Wapp@!*\n\nThis app only receives Audio, send a Voice Note for Transcript",
                webhook.user.user_id,
            )
