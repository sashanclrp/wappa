"""WhatsApp media rules from the live format matrix (2026-11-06).

Every case here was accepted by Meta with 200 and then failed as a 131053
status (or arrived broken); Wappa now refuses it before any call.
"""

from pathlib import Path

import pytest

from wappa.domain.inbox import InboxRef
from wappa.domain.interactive import CardMedia, MessageCard, ReplyButton
from wappa.domain.media_probe import probe
from wappa.messaging import DeliveryAddresses, DirectMessage
from wappa.messaging.whatsapp.media_rules import check_bytes, check_name
from wappa.messaging.whatsapp.messenger.whatsapp_messenger import (
    WhatsAppMessengerAdapter,
)

WA_DM = DirectMessage(
    inbox_ref=InboxRef.whatsapp("pnid"), addresses=DeliveryAddresses.of("573001112233")
)


class _Client:
    def __init__(self) -> None:
        self.posted: list[dict] = []

    async def post_request(self, payload):
        self.posted.append(payload)
        return {
            "messages": [{"id": "wamid.out"}],
            "contacts": [{"input": "573001112233", "wa_id": "573001112233"}],
        }


def _wa() -> tuple[WhatsAppMessengerAdapter, _Client]:
    client = _Client()
    messenger = WhatsAppMessengerAdapter(
        client=client,  # type: ignore[arg-type]
        media_handler=None,  # type: ignore[arg-type]
        interactive_handler=None,  # type: ignore[arg-type]
        template_handler=None,  # type: ignore[arg-type]
        specialized_handler=None,  # type: ignore[arg-type]
        inbox_id="pnid",
    )
    return messenger, client


def _webp_vp8x(width: int, height: int, *, animated: bool) -> bytes:
    flags = bytes([0x02 if animated else 0x00, 0, 0, 0])
    body = (
        b"VP8X"
        + (10).to_bytes(4, "little")
        + flags
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
    )
    return b"RIFF" + (len(body) + 4).to_bytes(4, "little") + b"WEBP" + body


OGG_VORBIS = b"OggS" + b"\x00" * 24 + b"\x01vorbis" + b"\x00" * 32
OGG_OPUS = b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 32
MP4_HEVC = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 12 + b"moov....stsd....hvc1"
MP4_H264 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 12 + b"moov....stsd....avc1"
GIF = b"GIF89a" + b"\x00" * 20


def test_probe_reads_what_a_name_cannot_show():
    assert probe(_webp_vp8x(240, 240, animated=True)).animated
    static = probe(_webp_vp8x(256, 256, animated=False))
    assert (static.mime, static.animated, static.width) == ("image/webp", False, 256)
    assert probe(OGG_VORBIS).codec == "vorbis"
    assert probe(OGG_OPUS).codec == "opus"
    assert probe(MP4_HEVC).codec == "hevc"
    assert probe(b"\x00\x00\x00\x18ftyp3gp4" + b"\x00" * 12).mime == "video/3gpp"
    assert probe(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 12).mime == "image/heic"
    assert probe(b"plain text").mime is None


@pytest.mark.parametrize(
    ("data", "use", "reason"),
    [
        (_webp_vp8x(240, 240, animated=True), "image", "animated WebP"),
        (GIF, "image", "image/gif"),
        (b"\x00\x00\x00\x18ftypheic" + b"\x00" * 12, "image", "image/heic"),
        (MP4_HEVC, "video", "HEVC"),
        (b"\x00\x00\x00\x18ftypqt  " + b"\x00" * 12, "video", "video/quicktime"),
        (b"\x1a\x45\xdf\xa3webm" + b"\x00" * 20, "video", "video/webm"),
        (OGG_VORBIS, "audio", "Opus"),
        (OGG_VORBIS, "voice", "Opus"),
        (b"\xff\xfb\x90\x00" + b"\x00" * 20, "voice", "audio/mpeg"),
        (b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 20, "audio", "audio/wav"),
        (_webp_vp8x(256, 256, animated=False), "sticker", "512x512"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 24, "sticker", "image/png"),
    ],
)
def test_content_whatsapp_rejects_is_refused(data: bytes, use: str, reason: str):
    with pytest.raises(ValueError, match=reason):
        check_bytes(data, use)


@pytest.mark.parametrize(
    ("data", "use"),
    [
        (_webp_vp8x(240, 240, animated=False), "image"),
        (MP4_H264, "video"),
        (OGG_OPUS, "voice"),
        (OGG_OPUS, "audio"),
        (_webp_vp8x(512, 512, animated=True), "sticker"),
        (b"unknown bytes", "image"),  # unknown content: Meta decides
    ],
)
def test_content_whatsapp_accepts_passes(data: bytes, use: str):
    check_bytes(data, use)


def test_sizes_are_capped():
    with pytest.raises(ValueError, match="limit"):
        check_bytes(b"\xff\xd8\xff" + b"\x00" * (5 * 1024 * 1024), "image")
    static_big = _webp_vp8x(512, 512, animated=False) + b"\x00" * (101 * 1024)
    with pytest.raises(ValueError, match="static sticker"):
        check_bytes(static_big, "sticker")


def test_names_are_checked_by_suffix_and_ids_pass():
    for name, use in (
        ("https://x.test/a.gif", "image"),
        ("https://x.test/a.heic?v=1", "image"),
        ("https://x.test/v.mov", "video"),
        ("https://x.test/v.webm", "video"),
        ("https://x.test/a.wav", "audio"),
    ):
        with pytest.raises(ValueError, match=f"WhatsApp {use} accepts"):
            check_name(name, use)
    check_name("https://x.test/v.3gp", "video")
    check_name("1234567890", "image")  # Media ID
    check_name("https://x.test/raw/42", "image")  # no suffix: Meta decides
    check_name("https://x.test/report.csv", "document")  # documents: any name


async def test_sends_refuse_before_any_call(tmp_path: Path):
    wa, client = _wa()
    files = {
        "anim.webp": _webp_vp8x(240, 240, animated=True),
        "clip.mp4": MP4_HEVC,
        "note.ogg": OGG_VORBIS,
        "small.webp": _webp_vp8x(256, 256, animated=False),
    }
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    with pytest.raises(ValueError, match="animated"):
        await wa.send_image(tmp_path / "anim.webp", WA_DM)
    with pytest.raises(ValueError, match="HEVC"):
        await wa.send_video(tmp_path / "clip.mp4", WA_DM)
    with pytest.raises(ValueError, match="Opus"):
        await wa.send_audio(tmp_path / "note.ogg", WA_DM, is_voice=True)
    with pytest.raises(ValueError, match="512x512"):
        await wa.send_sticker(tmp_path / "small.webp", WA_DM)
    with pytest.raises(ValueError, match="image accepts"):
        await wa.send_image("https://x.test/a.gif", WA_DM)
    with pytest.raises(ValueError, match="video accepts"):
        await wa.send_video("https://x.test/v.webm", WA_DM)
    assert client.posted == []
    assert (await wa.send_image("https://x.test/a.jpg", WA_DM)).success


async def test_carousel_checks_every_card_before_sending():
    wa, client = _wa()

    def card(url: str) -> MessageCard:
        return MessageCard(
            header=CardMedia.image(url=url),
            title="T",
            subtitle="s",
            buttons=(ReplyButton(id="ok", title="OK"),),
        )

    cards = [card("https://x.test/a.jpg"), card("https://x.test/b.gif")]
    with pytest.raises(ValueError, match="image accepts"):
        await wa.send_carousel(cards, WA_DM, "Pick one")
    assert client.posted == []


def test_instagram_takes_webp_by_url_only():
    """Live matrix 2026-11-06: a WebP renders on Instagram by URL, but the
    upload endpoint answers it with HTTP 500; an animated WebP shows only its
    first frame (GIF animates)."""
    from wappa.messaging.instagram.media import (
        MEDIA_RULES,
        check_upload_content,
        url_format_accepted,
        validate_upload,
    )

    assert ".webp" in MEDIA_RULES["image"].extensions
    assert url_format_accepted("https://x.test/a.webp", "image")
    with pytest.raises(ValueError, match="by URL"):
        validate_upload("a.webp", 10, "image")
    check_upload_content(GIF, "image")  # GIFs animate on Instagram
    with pytest.raises(ValueError, match="HTTP 500"):
        check_upload_content(_webp_vp8x(512, 512, animated=False), "image")
    with pytest.raises(ValueError, match="first frame"):
        check_upload_content(_webp_vp8x(512, 512, animated=True), "image")


def test_instagram_uploads_video_only_as_h264_mp4():
    """Live matrix 2026-11-06: WebM and MOV uploads answer HTTP 500; an HEVC
    MP4 uploads but its send is refused (3/1545003). WebM plays by URL; a MOV
    link shows an empty placeholder, so MOV is refused everywhere."""
    from wappa.messaging.instagram.media import (
        check_upload_content,
        url_format_accepted,
        validate_upload,
    )

    validate_upload("a.mp4", 10, "video")
    check_upload_content(MP4_H264, "video")
    with pytest.raises(ValueError, match="MP4 \\(H.264\\)"):
        validate_upload("a.webm", 10, "video")
    assert url_format_accepted("https://x.test/a.webm", "video")
    for name in ("a.mov", "a.ogg", "a.avi", "a.mkv", "a.3gp"):
        with pytest.raises(ValueError, match="does not convert media"):
            validate_upload(name, 10, "video")
        assert not url_format_accepted(f"https://x.test/{name}", "video")
    with pytest.raises(ValueError, match="HEVC"):
        check_upload_content(MP4_HEVC, "video")
