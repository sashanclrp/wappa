"""Typed instance attributes the ``WappaEventHandler`` lane mixins read.

``WappaEventHandler.__init__`` assigns them; the mixins only annotate them so
mypy can check lane code that lives outside ``base.py``.
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from wappa.core.logging.logger import ContextLogger
    from wappa.domain.inbox.identity import InboxRef
    from wappa.domain.interfaces.cache_factory import ICacheFactory
    from wappa.domain.interfaces.messaging_interface import IMessenger
    from wappa.messaging.instagram.platform_messenger import InstagramMessenger
    from wappa.messaging.whatsapp.platform_messenger import WhatsAppMessenger

    from ..default_handlers import (
        DefaultConversationEventHandler,
        DefaultErrorHandler,
        DefaultMessageHandler,
        DefaultStatusHandler,
        DefaultSystemHandler,
    )


class _HandlerState(ABC):
    """Attribute declarations shared by every lane mixin."""

    inbox_id: str | None
    inbox_ref: InboxRef | None
    user_id: str | None
    messenger: IMessenger | None
    whatsapp: WhatsAppMessenger | None
    instagram: InstagramMessenger | None
    cache_factory: ICacheFactory | None
    db: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None
    db_read: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None
    _scope_opener: Callable[..., AbstractAsyncContextManager[Self]] | None
    logger: ContextLogger
    _default_message_handler: DefaultMessageHandler
    _default_status_handler: DefaultStatusHandler
    _default_error_handler: DefaultErrorHandler
    _default_system_handler: DefaultSystemHandler
    _default_conversation_handler: DefaultConversationEventHandler
    _api_post_process_hooks: list[Callable[..., Any]]
