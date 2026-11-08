"""Instagram reaction message (ADR-0025 shape)."""

from __future__ import annotations

from wappa.schemas.core.types import UniversalMessageData
from wappa.webhooks.core.base_message import BaseReactionMessage

from ._base import InstagramMessageBase


class InstagramReactionMessage(InstagramMessageBase, BaseReactionMessage):
    """A User reacted to (or removed a reaction from) a message, ADR-0025 shape.

    Instagram gives a reaction no message ID of its own, so ``id`` is
    ``reaction:<target mid>:<timestamp ms>``.
    """

    target_mid: str
    action: str
    reaction_name: str | None = None
    emoji_value: str | None = None

    @property
    def target_message_id(self) -> str:
        return self.target_mid

    @property
    def emoji(self) -> str:
        return "" if self.is_removal else (self.emoji_value or "")

    @property
    def is_removal(self) -> bool:
        return self.action == "unreact"

    def to_universal_dict(self) -> UniversalMessageData:
        from wappa.webhooks.core.base_message.projections import reaction_projection

        return reaction_projection(self)
