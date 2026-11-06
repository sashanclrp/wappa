"""WhatsApp media rules, enforced before any Cloud API call.

Built from Meta's docs and the live format matrix of 2026-11-06 (Instagram
conversations PRD, ``references/media-formats.md``): a link Meta cannot use is still
accepted with 200 and fails later as a ``failed`` status (131053), so Wappa
refuses what it can tell up front. A name's suffix is checked when it has one;
a local file or bytes are also probed (``wappa.domain.media_probe``) for what
a suffix cannot show: animated WebP, OGG Vorbis, HEVC, sticker size.

Every refusal is ``ValueError``. Wappa never converts media: the Host prepares
files in a format that fits (the reference lists the recommended ones).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from wappa.domain.media_probe import MediaProbe, probe
from wappa.domain.media_renditions import media_suffix

MB = 1024 * 1024
KB = 1024


@dataclass(frozen=True, slots=True)
class WhatsAppMediaRule:
    suffixes: frozenset[str] | None  # None: any name (documents)
    mimes: frozenset[str] | None  # None: any content
    max_bytes: int


RULES: dict[str, WhatsAppMediaRule] = {
    "image": WhatsAppMediaRule(
        frozenset({".jpg", ".jpeg", ".png", ".webp"}),
        frozenset({"image/jpeg", "image/png", "image/webp"}),
        5 * MB,
    ),
    "video": WhatsAppMediaRule(
        frozenset({".mp4", ".3gp"}),
        frozenset({"video/mp4", "video/3gpp"}),
        16 * MB,
    ),
    "audio": WhatsAppMediaRule(
        frozenset({".aac", ".amr", ".mp3", ".m4a", ".ogg"}),
        frozenset({"audio/aac", "audio/amr", "audio/mpeg", "audio/mp4", "audio/ogg"}),
        16 * MB,
    ),
    "voice": WhatsAppMediaRule(frozenset({".ogg"}), frozenset({"audio/ogg"}), 16 * MB),
    "sticker": WhatsAppMediaRule(
        frozenset({".webp"}), frozenset({"image/webp"}), 500 * KB
    ),
    "document": WhatsAppMediaRule(None, None, 100 * MB),
}

STICKER_SIZE = (512, 512)
STICKER_STATIC_MAX = 100 * KB


def check_name(name: str, use: str) -> None:
    """Refuse a URL or file name whose suffix WhatsApp does not take for ``use``.

    A name without a suffix (a Media ID, an extension-less URL) passes.
    """
    rule = RULES[use]
    suffix = media_suffix(name)
    if rule.suffixes is None or not suffix or suffix in rule.suffixes:
        return
    raise ValueError(
        f"WhatsApp {use} accepts {', '.join(sorted(rule.suffixes))}; got {suffix}"
        "; convert it before sending (Wappa does not convert media)"
    )


def check_bytes(data: bytes, use: str, *, name: str | None = None) -> MediaProbe:
    """Refuse content WhatsApp rejects for ``use``; return what was read."""
    rule = RULES[use]
    if name:
        check_name(name, use)
    found = probe(data)
    if found.size > rule.max_bytes:
        raise ValueError(
            f"WhatsApp {use} is {found.size} bytes; limit is {rule.max_bytes}"
        )
    if rule.mimes is None or found.mime is None:
        return found  # unknown content: Meta decides
    if found.mime not in rule.mimes:
        raise ValueError(
            f"WhatsApp {use} accepts {', '.join(sorted(rule.mimes))}; "
            f"this file is {found.mime}"
            "; convert it before sending (Wappa does not convert media)"
        )
    _check_content(found, use)
    return found


def check_file(path: Path, use: str, *, by_name: bool = True) -> MediaProbe | None:
    """``check_bytes`` for a local file; a document is checked by size only.

    ``by_name=False`` skips the suffix check (the caller named the MIME type).
    """
    rule = RULES[use]
    if by_name:
        check_name(path.name, use)
    size = path.stat().st_size
    if size > rule.max_bytes:
        raise ValueError(f"WhatsApp {use} is {size} bytes; limit is {rule.max_bytes}")
    if rule.mimes is None:
        return None
    return check_bytes(path.read_bytes(), use)


def _check_content(found: MediaProbe, use: str) -> None:
    if use == "image" and found.animated:
        raise ValueError(
            "WhatsApp image does not take animated WebP (131053); send a static "
            "image, or the animation as an MP4 video"
        )
    if use == "video" and found.codec == "hevc":
        raise ValueError(
            "WhatsApp video needs H.264 video (and AAC audio); this file is HEVC (131053)"
        )
    if (
        use in ("audio", "voice")
        and found.mime == "audio/ogg"
        and found.codec != "opus"
    ):
        raise ValueError(
            f"WhatsApp {use} takes OGG only with the Opus codec; this file is "
            f"{found.codec or 'not Opus'} (131053)"
        )
    if use == "sticker":
        if (found.width, found.height) != STICKER_SIZE and found.width is not None:
            raise ValueError(
                f"WhatsApp sticker must be 512x512; this one is "
                f"{found.width}x{found.height} (131053)"
            )
        if not found.animated and found.size > STICKER_STATIC_MAX:
            raise ValueError(
                f"WhatsApp static sticker is {found.size} bytes; limit is "
                f"{STICKER_STATIC_MAX}"
            )


__all__ = ["RULES", "check_bytes", "check_file", "check_name"]
