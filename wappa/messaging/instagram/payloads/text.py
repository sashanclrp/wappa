"""Text checks, the byte-limit splitter and the header/body/footer fold."""

from __future__ import annotations

from ..limits import TEXT_MAX_BYTES


def check_instagram_text(text: str, *, what: str = "Instagram text") -> str:
    if not text or not text.strip():
        raise ValueError(f"{what} must not be empty")
    size = len(text.encode("utf-8"))
    if size > TEXT_MAX_BYTES:
        raise ValueError(f"{what} is {size} UTF-8 bytes; limit is {TEXT_MAX_BYTES}")
    return text


def split_text(text: str, limit: int = TEXT_MAX_BYTES) -> list[str]:
    """Split ``text`` into chunks of at most ``limit`` UTF-8 bytes.

    Cuts on the last newline or space that fits, and mid-word only when a
    single word is longer than the limit.
    """
    if len(text.encode("utf-8")) <= limit:
        return [text]
    chunks: list[str] = []
    rest = text.strip()
    while len(rest.encode("utf-8")) > limit:
        cut = len(rest.encode("utf-8")[:limit].decode("utf-8", "ignore"))
        space = max(rest.rfind("\n", 0, cut + 1), rest.rfind(" ", 0, cut + 1))
        if space > 0:
            cut = space
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        chunks.append(rest)
    return chunks


def check_len(value: str, limit: int, what: str) -> str:
    if len(value) > limit:
        raise ValueError(f"{what} is {len(value)} characters; limit is {limit}")
    return value


def fold(*parts: str | None) -> str:
    """Join header/body/footer for Platforms without separate slots."""
    return "\n\n".join(p.strip() for p in parts if p and p.strip())
