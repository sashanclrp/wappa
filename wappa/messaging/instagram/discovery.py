"""Instagram operation semantics and limits derived from adapter rules."""

from wappa.domain.messenger_discovery import (
    MediaLimit,
    MessageLimits,
    MessengerDiscovery,
)
from wappa.messaging.instagram.media.rules import MEDIA_RULES, URL_ONLY, mime_for


def discovery(operations: frozenset[str]) -> MessengerDiscovery:
    limits = {
        family: MediaLimit(
            extensions=tuple(sorted(rule.extensions)),
            upload_extensions=tuple(
                sorted(rule.extensions - URL_ONLY.get(family, frozenset()))
            ),
            mime_types=tuple(
                sorted({mime_for("file" + suffix) for suffix in rule.extensions})
            ),
            max_bytes=rule.max_bytes,
            constraints={
                "image": ("WebP by URL only; animated WebP shows first frame",),
                "video": ("Upload MP4 with H.264; WebM by URL only",),
            }.get(family, ()),
        )
        for family, rule in MEDIA_RULES.items()
    }
    limits["sticker"] = limits["image"]
    return MessengerDiscovery(
        operations=operations,
        media_operations=frozenset({"upload", "download"}),
        typing=True,
        read_scope="thread",
        target_kinds=frozenset({"direct_message", "private_reply"}),
        message_limits=MessageLimits(
            max_text_length=4096, native_text_max_bytes=1000, splits_text=True
        ),
        media_limits=limits,
        media_http_limits={
            "max_caption_length": 1024,
            "max_file_sizes": {
                family: limit.max_bytes for family, limit in limits.items()
            },
            "supported_media_types": {
                family: limit.mime_types for family, limit in limits.items()
            },
        },
    )
