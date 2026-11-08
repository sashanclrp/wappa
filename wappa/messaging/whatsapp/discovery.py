"""WhatsApp operation semantics and limits derived from adapter rules."""

from wappa.domain.messenger_discovery import (
    MediaLimit,
    MessageLimits,
    MessengerDiscovery,
)
from wappa.messaging.whatsapp.media.rules import RULES
from wappa.messaging.whatsapp.payloads import WhatsAppMediaPayloadBuilder


def discovery(operations: frozenset[str]) -> MessengerDiscovery:
    return MessengerDiscovery(
        operations=operations,
        media_operations=frozenset({"upload", "download", "info", "delete"}),
        typing=True,
        read_scope="message",
        message_limits=MessageLimits(
            max_text_length=4096,
            max_preview_url_text_length=4096,
            max_recipient_phone_length=20,
        ),
        media_limits={
            family: MediaLimit(
                extensions=tuple(sorted(rule.suffixes)) if rule.suffixes else None,
                upload_extensions=tuple(sorted(rule.suffixes))
                if rule.suffixes
                else None,
                mime_types=tuple(sorted(rule.mimes)) if rule.mimes else None,
                max_bytes=rule.max_bytes,
                constraints={
                    "video": ("H.264 video and AAC audio",),
                    "audio": ("OGG requires Opus",),
                    "voice": ("OGG requires Opus",),
                    "image": ("Static images only",),
                    "sticker": ("512x512; static <= 100 KiB; animated <= 500 KiB",),
                }.get(family, ()),
            )
            for family, rule in RULES.items()
        },
        media_http_limits=WhatsAppMediaPayloadBuilder().get_media_limits(),
    )
