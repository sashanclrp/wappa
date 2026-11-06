"""What a media file really is, read from its bytes (Platform-neutral).

``probe`` reads magic bytes and container headers only: no decoding, no
third-party dependency. It answers the questions the live format matrix
(2026-11-06) showed a file name cannot: animated or static WebP, Opus or
Vorbis inside OGG, HEVC or H.264 inside MP4, and image dimensions. Platform
rules live with each adapter and refuse a non-conforming file before any
call; Wappa never converts media.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# Enough for every header below; the video codec scan reads the whole file.
HEADER_BYTES = 64


@dataclass(frozen=True, slots=True)
class MediaProbe:
    """The facts read from a file's bytes. ``mime`` is None when unknown."""

    mime: str | None
    size: int
    animated: bool = False
    width: int | None = None
    height: int | None = None
    codec: str | None = None  # "opus" / "vorbis" (OGG), "h264" / "hevc" (MP4)


def probe(data: bytes) -> MediaProbe:
    """Read ``data``'s real type; unknown formats return ``mime=None``."""
    size = len(data)
    head = data[:HEADER_BYTES]
    if head.startswith(b"\xff\xd8\xff"):
        return MediaProbe("image/jpeg", size)
    if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
        width, height = struct.unpack(">II", head[16:24])
        return MediaProbe("image/png", size, width=width, height=height)
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return MediaProbe("image/gif", size, animated=data.count(b"\x21\xf9\x04") > 1)
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return _webp(data, size)
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return MediaProbe("audio/wav", size)
    if head[4:8] == b"ftyp":
        return _iso_bmff(data, size)
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        mime = "video/webm" if b"webm" in head else "video/x-matroska"
        return MediaProbe(mime, size)
    if head.startswith(b"OggS"):
        codec = (
            "opus" if b"OpusHead" in head else "vorbis" if b"vorbis" in head else None
        )
        return MediaProbe("audio/ogg", size, codec=codec)
    if head.startswith(b"#!AMR"):
        return MediaProbe("audio/amr", size)
    if head.startswith(b"ID3"):
        return MediaProbe("audio/mpeg", size)
    if len(head) >= 2 and head[0] == 0xFF:
        if head[1] & 0xF6 == 0xF0:  # ADTS sync with layer 00
            return MediaProbe("audio/aac", size)
        if head[1] & 0xE0 == 0xE0:  # MPEG audio frame sync
            return MediaProbe("audio/mpeg", size)
    if head.startswith(b"%PDF"):
        return MediaProbe("application/pdf", size)
    return MediaProbe(None, size)


def _webp(data: bytes, size: int) -> MediaProbe:
    chunk = data[12:16]
    width = height = None
    animated = False
    if chunk == b"VP8X" and len(data) >= 30:
        animated = bool(data[20] & 0x02)
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
    elif chunk == b"VP8 " and len(data) >= 30:
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
    elif chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
    return MediaProbe("image/webp", size, animated=animated, width=width, height=height)


_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"heim", b"heis"}


def _iso_bmff(data: bytes, size: int) -> MediaProbe:
    brand = data[8:12]
    if brand in _HEIF_BRANDS:
        return MediaProbe("image/heic", size)
    if brand == b"avif":
        return MediaProbe("image/avif", size)
    if brand in (b"M4A ", b"M4B "):
        return MediaProbe("audio/mp4", size)
    if brand == b"qt  ":
        mime = "video/quicktime"
    elif brand.startswith(b"3gp") or brand.startswith(b"3g2"):
        mime = "video/3gpp"
    else:
        mime = "video/mp4"
    # The sample entry names the codec (stsd); moov may sit at either end.
    if b"hvc1" in data or b"hev1" in data:
        codec: str | None = "hevc"
    elif b"avc1" in data:
        codec = "h264"
    else:
        codec = None
    if (
        mime == "video/mp4"
        and codec is None
        and b"mp4a" in data
        and b"vide" not in data
    ):
        mime = "audio/mp4"  # an audio-only MP4 (M4A without the M4A brand)
    return MediaProbe(mime, size, codec=codec)


__all__ = ["HEADER_BYTES", "MediaProbe", "probe"]
