"""Parsing of Instagram post and comment reads into the neutral content values."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interfaces.conversation_capabilities import (
    CommentContent,
    ContentPage,
    PostChild,
    PostContent,
)
from wappa.domain.messaging_targets import CommentRef, PostRef


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("+0000", "+00:00"))
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_post(ref: PostRef, body: dict[str, Any]) -> PostContent:
    children_raw = body.get("children")
    children: list[PostChild] = []
    if isinstance(children_raw, dict):
        for child in children_raw.get("data", []) or []:
            if isinstance(child, dict) and _str(child.get("id")):
                children.append(
                    PostChild(
                        media_id=child["id"],
                        media_type=_str(child.get("media_type")),
                        media_url=_str(child.get("media_url")),
                        thumbnail_url=_str(child.get("thumbnail_url")),
                        permalink=_str(child.get("permalink")),
                    )
                )
    enabled = body.get("is_comment_enabled")
    return PostContent(
        post_ref=ref,
        media_type=_str(body.get("media_type")),
        media_product_type=_str(body.get("media_product_type")),
        caption=_str(body.get("caption")),
        permalink=_str(body.get("permalink")),
        media_url=_str(body.get("media_url")),
        thumbnail_url=_str(body.get("thumbnail_url")),
        timestamp=_when(body.get("timestamp")),
        username=_str(body.get("username")),
        comments_count=_int(body.get("comments_count")),
        like_count=_int(body.get("like_count")),
        is_comment_enabled=enabled if isinstance(enabled, bool) else None,
        children=tuple(children),
        raw=body,
    )


def parse_comment(inbox_ref: InboxRef, body: dict[str, Any]) -> CommentContent | None:
    comment_id = _str(body.get("id"))
    if not comment_id:
        return None
    author = _dict(body.get("from"))
    media = _dict(body.get("media"))
    hidden = body.get("hidden")
    return CommentContent(
        comment_ref=CommentRef(inbox_ref=inbox_ref, comment_id=comment_id),
        text=_str(body.get("text")),
        timestamp=_when(body.get("timestamp")),
        author_id=_str(author.get("id")),
        author_username=_str(author.get("username")) or _str(body.get("username")),
        parent_comment_id=_str(body.get("parent_id")),
        media_id=_str(media.get("id")),
        hidden=hidden if isinstance(hidden, bool) else None,
        like_count=_int(body.get("like_count")),
        raw=body,
    )


def parse_page(
    inbox_ref: InboxRef, body: dict[str, Any]
) -> ContentPage[CommentContent]:
    items = [
        parsed
        for raw in body.get("data", []) or []
        if isinstance(raw, dict)
        and (parsed := parse_comment(inbox_ref, raw)) is not None
    ]
    paging = _dict(body.get("paging"))
    cursors = _dict(paging.get("cursors"))
    after = _str(cursors.get("after")) if paging.get("next") else None
    return ContentPage[CommentContent](items=tuple(items), next_cursor=after)
