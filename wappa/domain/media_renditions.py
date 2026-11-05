"""Pick the media rendition a Platform accepts.

Platforms disagree on formats for the same action: WhatsApp stickers must be
WebP, while Instagram (which sends a sticker as an image) takes png/jpeg/gif
only. A Host passes every rendition it has; each Platform adapter picks the
first one its Platform accepts. Wappa never converts media.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

type MediaSource = str | Path
type MediaRenditions = MediaSource | Sequence[MediaSource]


def media_suffix(source: MediaSource) -> str:
    """Lower-case file extension of a path or URL path; ``""`` for media IDs."""
    raw = str(source)
    path = urlsplit(raw).path if "://" in raw else raw
    return PurePosixPath(path).suffix.lower()


def pick_rendition(
    renditions: MediaRenditions,
    accepted_suffixes: frozenset[str],
    *,
    what: str,
) -> MediaSource:
    """Return the first rendition with an accepted extension.

    A single source without an extension (a Platform media ID or an
    extension-less URL) is passed through, since its format cannot be told
    from its name. Raises ``ValueError`` when nothing fits.
    """
    sources: list[MediaSource] = (
        [renditions] if isinstance(renditions, (str, Path)) else list(renditions)
    )
    if not sources:
        raise ValueError(f"{what} needs at least one media source")
    for source in sources:
        if media_suffix(source) in accepted_suffixes:
            return source
    if len(sources) == 1 and not media_suffix(sources[0]):
        return sources[0]
    found = sorted({media_suffix(s) or "no extension" for s in sources})
    raise ValueError(
        f"{what} accepts {', '.join(sorted(accepted_suffixes))}; got {', '.join(found)}"
    )


__all__ = ["MediaRenditions", "MediaSource", "media_suffix", "pick_rendition"]
