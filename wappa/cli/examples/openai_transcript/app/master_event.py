import os

from openai import AsyncOpenAI

from wappa import WappaEventHandler
from wappa.core.logging import get_logger
from wappa.domain.inbox import InboxRef
from wappa.messaging import DirectMessage
from wappa.webhooks import InboundMessageWebhook
from wappa.webhooks.core.base_message import BaseAudioMessage

from .openai_utils import AudioProcessingService

logger = get_logger("TranscriptEventHandler")


class TranscriptEventHandler(WappaEventHandler):
    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        messenger = self.messenger
        if messenger is None:
            return
        reply_to = DirectMessage(
            inbox_ref=InboxRef(
                platform=messenger.platform, inbox_id=messenger.inbox_id
            ),
            addresses=webhook.user.delivery_addresses(),
        )

        await messenger.mark_as_read(webhook.message.message_id, reply_to)

        if not isinstance(webhook.message, BaseAudioMessage):
            await messenger.send_text(
                "*Hey Wapp@!*\n\nThis app only receives Audio, send a Voice Note for Transcript",
                reply_to,
            )
            return

        # The shared media seam: the same call on WhatsApp and Instagram.
        # Pass the webhook's media_id unchanged; the bytes stay in memory.
        download = await messenger.media.download(webhook.message.media_id)
        if not download.found or download.value is None:
            logger.error(f"Failed to download audio: {download.error}")
            await messenger.send_text(
                "Sorry, I couldn't download the audio file.", reply_to
            )
            return

        audio = download.value
        openai_client = AsyncOpenAI(api_key=os.environ["LLM_PROVIDER_OPENAI_API_KEY"])
        audio_service = AudioProcessingService(openai_client)
        # The extension tells OpenAI the format: "audio/ogg; codecs=opus" -> ogg
        subtype = (audio.content_type or "audio/ogg").split("/")[-1].split(";")[0]
        transcription = await audio_service.transcribe_audio(
            audio.content, f"audio.{subtype.strip()}"
        )
        await messenger.send_text(f"*Transcript:*\n\n{transcription}", reply_to)
        logger.info(f"Transcribed audio from memory ({audio.size} bytes)")
