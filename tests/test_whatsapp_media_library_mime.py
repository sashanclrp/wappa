"""WhatsApp uploads infer the MIME type from the name and the family."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from wappa.domain.interfaces.media_library import MediaFamily
from wappa.messaging.whatsapp.media.library import WhatsAppMediaLibrary


class _Handler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def upload_media(self, source, *, media_type=None, filename=None):
        self.calls.append(("path", media_type))
        return SimpleNamespace(success=True, media_id="m1")

    async def upload_media_from_bytes(self, data, mime, name):
        self.calls.append(("bytes", mime))
        return SimpleNamespace(success=True, media_id="m1")


@pytest.mark.asyncio
async def test_a_3gp_video_uploads_as_video_3gpp(tmp_path: Path) -> None:
    clip = tmp_path / "clip.3gp"
    clip.write_bytes(b"x")
    handler = _Handler()
    library = WhatsAppMediaLibrary(handler, "pnid")  # type: ignore[arg-type]

    await library.upload(clip, MediaFamily.VIDEO)
    await library.upload(b"x", MediaFamily.VIDEO, filename="clip.3gp")
    with pytest.raises(ValueError, match="WhatsApp audio accepts"):
        await library.upload(b"x", MediaFamily.AUDIO, filename="note.3gp")
    await library.upload(clip, MediaFamily.VIDEO, mime_type="video/mp4")

    assert handler.calls == [
        ("path", "video/3gpp"),
        ("bytes", "video/3gpp"),
        ("path", "video/mp4"),
    ]
