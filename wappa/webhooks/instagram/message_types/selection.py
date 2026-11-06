"""Instagram selections: postback button taps and quick replies."""

from __future__ import annotations

from pydantic import ConfigDict

from wappa.schemas.core.types import InteractiveType, UniversalMessageData
from wappa.webhooks.core.base_message import BaseInteractiveMessage

from ._base import InstagramMessageBase


class InstagramButtonReplyMessage(InstagramMessageBase, BaseInteractiveMessage):
    """A postback button tap, normalized like a WhatsApp ``button_reply``.

    Instagram delivers it on ``messaging_postbacks`` with no visible message;
    Wappa presents it as an interactive message (ADR-0025) so Hosts read one
    selection shape on every Platform.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    title: str
    payload: str

    @property
    def interactive_type(self) -> InteractiveType:
        return InteractiveType.BUTTON_REPLY

    @property
    def selected_option_id(self) -> str:
        return self.payload

    @property
    def selected_option_title(self) -> str:
        return self.title

    @property
    def text_content(self) -> str:
        return self.title

    @property
    def original_message_id(self) -> str:
        return ""

    @property
    def is_button_reply(self) -> bool:
        return True

    @property
    def is_list_reply(self) -> bool:
        return False

    def to_universal_dict(self) -> UniversalMessageData:
        return self._universal(text=self.title, selection=self.payload)


class InstagramQuickReplyMessage(InstagramMessageBase, BaseInteractiveMessage):
    """A quick-reply selection: text the User saw plus the action payload.

    One native event → one InboundMessageWebhook; never also an Interaction.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    text: str
    payload: str

    @property
    def interactive_type(self) -> InteractiveType:
        return InteractiveType.QUICK_REPLY

    @property
    def selected_option_id(self) -> str:
        return self.payload

    @property
    def selected_option_title(self) -> str:
        return self.text

    @property
    def text_content(self) -> str:
        return self.text

    @property
    def original_message_id(self) -> str:
        return ""

    @property
    def is_button_reply(self) -> bool:
        return False

    @property
    def is_list_reply(self) -> bool:
        return False

    @property
    def is_quick_reply(self) -> bool:
        return True

    def to_universal_dict(self) -> UniversalMessageData:
        return self._universal(text=self.text, selection=self.payload)
