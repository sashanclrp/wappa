# OpenAI Transcription Example

Transcribes WhatsApp voice notes with OpenAI Whisper and replies with the text. It is the smallest example that downloads media, so it is the one to copy when your handler needs the bytes of an inbound file rather than just its ID.

## What it demonstrates

- Downloading inbound media through `messenger.media_handler.download_media_tempfile(media_id)`, an async context manager that cleans the temporary file up for you
- Narrowing a webhook to a concrete message type (`WhatsAppAudioMessage`) before touching Platform-specific fields
- Calling a third-party async API (`AsyncOpenAI`) from inside an event handler
- `mark_as_read()` as an immediate acknowledgement while slower work continues

## Setup

```bash
uv sync
```

Create a `.env` file in the project root:

```env
# Meta application — required whenever the WhatsApp callback is mounted (no dev bypass)
META_APP_SECRET=your_meta_app_secret_here
WP_WEBHOOK_VERIFY_TOKEN=your_verify_token_here

# Legacy single-Inbox credential bundle
WP_ACCESS_TOKEN=your_access_token_here
WP_PHONE_ID=your_phone_number_id_here
WP_BID=your_business_id_here

# Transcription
OPENAI_API_KEY=your_openai_api_key_here
```

## Run

```bash
uv run wappa dev app/main.py
```

Point the Meta callback at `https://<your-host>/webhook/inboxes/whatsapp` — the same URL serves the `GET` verification challenge and the `POST` deliveries, and Wappa derives the Inbox from the authenticated payload.

## Files

| Path | Role |
|---|---|
| `app/main.py` | Builds the `Wappa` app and registers the handler |
| `app/master_event.py` | `TranscriptEventHandler` — downloads the audio, transcribes it, replies |
| `app/openai_utils/audio_processing.py` | `AudioProcessingService` wrapper around the Whisper call |

## Notes

Transcription costs money per request and takes seconds, so a production version should bound the audio length it accepts, handle the OpenAI error paths explicitly, and move the transcription off the webhook request path. Wappa delivers events at least once — Meta retries — so make the work idempotent on `message_id` before you bill against it.
