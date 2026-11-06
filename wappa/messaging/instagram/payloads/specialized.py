"""Text stand-ins for what Instagram has no native message for: documents and contacts."""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from wappa.domain.contacts import ContactCard


def document_link(url: str, filename: str | None) -> str:
    """The text that shares a document Instagram cannot attach: name and link."""
    name = filename or unquote(PurePosixPath(urlsplit(url).path).name) or url
    return f"📄 {name}\n{url}"


def contact_text(card: ContactCard) -> str:
    lines = [f"👤 {card.name.formatted_name}"]
    if card.org and (card.org.company or card.org.title):
        lines.append(" · ".join(p for p in (card.org.title, card.org.company) if p))
    lines += [f"📞 {p.phone}" for p in card.phones or []]
    lines += [f"✉️ {e.email}" for e in card.emails or []]
    lines += [f"🔗 {u.url}" for u in card.urls or []]
    return "\n".join(lines)
