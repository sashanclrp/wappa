"""Typed webhook contracts for WhatsApp Business App Coexistence events."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wappa.webhooks.whatsapp.base_models import WhatsAppContact, WhatsAppMetadata


class CoexistenceModel(BaseModel):
    """Strict base for Meta Coexistence payload components."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class HistoryContext(CoexistenceModel):
    """Identity attached to a synced chat-history thread."""

    wa_id: str | None = None
    user_id: str
    parent_user_id: str | None = None
    username: str | None = None


class HistoryMessageContext(CoexistenceModel):
    """Delivery state recorded for a synced message."""

    status: str


class CoexistenceMessage(CoexistenceModel):
    """Message envelope used by history and SMB echo webhooks.

    Meta places the message body below a key matching ``type``. The known
    message keys remain explicit so an upstream addition triggers the standard
    contract-drift alert instead of being discarded.
    """

    from_: str | None = Field(default=None, alias="from")
    from_user_id: str | None = None
    from_parent_user_id: str | None = None
    to: str | None = None
    to_user_id: str | None = None
    to_parent_user_id: str | None = None
    id: str
    timestamp: str
    type: str
    context: dict[str, Any] | None = None
    history_context: HistoryMessageContext | None = None
    text: dict[str, Any] | None = None
    image: dict[str, Any] | None = None
    audio: dict[str, Any] | None = None
    video: dict[str, Any] | None = None
    document: dict[str, Any] | None = None
    sticker: dict[str, Any] | None = None
    contacts: list[dict[str, Any]] | None = None
    location: dict[str, Any] | None = None
    interactive: dict[str, Any] | None = None
    button: dict[str, Any] | None = None
    order: dict[str, Any] | None = None
    reaction: dict[str, Any] | None = None
    system: dict[str, Any] | None = None
    unsupported: dict[str, Any] | None = None
    revoke: dict[str, Any] | None = None
    edit: dict[str, Any] | None = None


class HistoryThread(CoexistenceModel):
    """One conversation included in a history sync chunk."""

    id: str | None = None
    context: HistoryContext
    messages: list[CoexistenceMessage]


class HistoryMetadata(CoexistenceModel):
    """Progress metadata for a history sync chunk."""

    phase: int | str
    chunk_order: int
    progress: int


class HistoryChunk(CoexistenceModel):
    """A chunk of synced WhatsApp Business App history."""

    metadata: HistoryMetadata
    threads: list[HistoryThread]


class HistoryWebhookValue(CoexistenceModel):
    """Strict value for the ``history`` field.

    History syncs use ``history`` chunks. Media syncs use the same field with
    top-level contacts plus either ``messages`` or ``message_echoes``.
    """

    messaging_product: Literal["whatsapp"]
    metadata: WhatsAppMetadata
    history: list[HistoryChunk] | None = None
    contacts: list[WhatsAppContact] | None = None
    messages: list[CoexistenceMessage] | None = None
    message_echoes: list[CoexistenceMessage] | None = None

    @model_validator(mode="after")
    def require_history_content(self) -> "HistoryWebhookValue":
        if not any((self.history, self.messages, self.message_echoes)):
            raise ValueError(
                "history webhook requires history, messages, or message_echoes"
            )
        return self


class SmbMessageEchoesWebhookValue(CoexistenceModel):
    """Strict value for the ``smb_message_echoes`` field."""

    messaging_product: Literal["whatsapp"]
    metadata: WhatsAppMetadata
    contacts: list[WhatsAppContact]
    message_echoes: list[CoexistenceMessage]


class AppStateContact(CoexistenceModel):
    """A contact synchronized from the WhatsApp Business app."""

    full_name: str
    first_name: str
    phone_number: str | None = None
    user_id: str
    parent_user_id: str | None = None
    username: str | None = None


class AppStateMetadata(CoexistenceModel):
    """Timestamp attached to an app state change."""

    timestamp: str


class AppStateSyncEntry(CoexistenceModel):
    """One Coexistence app state mutation."""

    type: Literal["contact"]
    contact: AppStateContact
    action: str
    metadata: AppStateMetadata


class SmbAppStateSyncWebhookValue(CoexistenceModel):
    """Strict value for the ``smb_app_state_sync`` field."""

    messaging_product: Literal["whatsapp"]
    metadata: WhatsAppMetadata
    state_sync: list[AppStateSyncEntry]


CoexistenceWebhookValue = (
    HistoryWebhookValue | SmbMessageEchoesWebhookValue | SmbAppStateSyncWebhookValue
)
