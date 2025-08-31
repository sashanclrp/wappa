# Removed direct config import
# from config.env import OPENAI_API_KEY
import io
from pathlib import Path
from typing import BinaryIO

from openai import AsyncOpenAI

from wappa.core.logging import get_logger  # Corrected relative import

# Initialize logger with class name
logger = get_logger("AudioProcessingService")


class AudioProcessingService:
    def __init__(self, async_openai_client: AsyncOpenAI):
        # Accept api_key in init
        self.async_openai_client = async_openai_client

    async def transcribe_audio(
        self, audio_source: str | Path | bytes | BinaryIO, filename: str = "audio"
    ) -> str:
        """
        Transcribes the audio using OpenAI's speech-to-text API with the gpt-4o-mini-transcribe model.

        Args:
            audio_source: Can be:
                - str/Path: Path to the audio file to transcribe
                - bytes: Raw audio data
                - BinaryIO: File-like object containing audio data
            filename: Name for the audio (used for OpenAI API, especially for bytes/BinaryIO)

        Returns:
            The transcribed text.
        """
        try:
            # Handle different input types
            if isinstance(audio_source, str | Path):
                # File path input (original behavior)
                audio_path = Path(audio_source)
                with audio_path.open("rb") as audio_file:
                    transcription = (
                        await self.async_openai_client.audio.transcriptions.create(
                            model="gpt-4o-mini-transcribe",
                            file=audio_file,
                            response_format="json",
                        )
                    )
                logger.debug(f"Transcription successful for file: {audio_path}")

            elif isinstance(audio_source, bytes):
                # Bytes input - create BytesIO stream
                audio_stream = io.BytesIO(audio_source)
                audio_stream.name = filename  # OpenAI API needs a filename attribute
                transcription = (
                    await self.async_openai_client.audio.transcriptions.create(
                        model="gpt-4o-mini-transcribe",
                        file=audio_stream,
                        response_format="json",
                    )
                )
                logger.debug(
                    f"Transcription successful for bytes data ({len(audio_source)} bytes)"
                )

            else:
                # File-like object input
                # Ensure it has a name attribute for OpenAI API
                if not hasattr(audio_source, "name"):
                    audio_source.name = filename
                transcription = (
                    await self.async_openai_client.audio.transcriptions.create(
                        model="gpt-4o-mini-transcribe",
                        file=audio_source,
                        response_format="json",
                    )
                )
                logger.debug(
                    f"Transcription successful for file-like object: {getattr(audio_source, 'name', 'unknown')}"
                )

            return transcription.text

        except FileNotFoundError:
            logger.error(f"Audio file not found for transcription: {audio_source}")
            raise
        except Exception as e:
            logger.error(f"Error during OpenAI transcription call: {e}", exc_info=True)
            raise
