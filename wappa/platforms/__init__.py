"""Platform Registry: the composition root for installed Platforms.

``PLATFORMS.keys()`` is the one installed-Platform set. Each Platform has one
module here (``whatsapp.py``, ``instagram.py``) that wires its inbound
``PlatformWebhooks`` adapter, its Messenger builder and, optionally, its
Platform Messenger builder (the Host-facing ``self.whatsapp`` /
``self.instagram`` on the handler). ``PlatformType`` is vocabulary: a member
with no entry (Telegram, Teams) is reserved, not installed, and every lookup of
a missing key fails loudly instead of falling through to another Platform.

Platform-specific imports and branches are legitimate only in this package and
in the adapter folders. A new Platform adds its adapters, one module here with
``PLATFORM``, ``BUILTIN_FIELDS`` and ``entry()``, and one line in ``_INSTALLED``.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING

from wappa.core.events.field_registry import FieldHandlerRegistry
from wappa.schemas.core.types import PlatformType

from . import instagram, whatsapp
from .entry import (
    MessengerBuilder,
    MessengerDeps,
    PlatformEntry,
    PlatformMessengerBuilder,
)

if TYPE_CHECKING:
    from wappa.domain.interfaces.messaging_interface import IMessenger

_INSTALLED = (whatsapp, instagram)

BUILTIN_FIELDS: Mapping[PlatformType, frozenset[str]] = MappingProxyType(
    {module.PLATFORM: module.BUILTIN_FIELDS for module in _INSTALLED}
)
"""Each installed Platform's reserved webhook fields; seeds ``FieldHandlerRegistry``."""


def build_platforms(
    field_registry: FieldHandlerRegistry,
) -> Mapping[PlatformType, PlatformEntry]:
    """Build the installed-Platform table bound to one app's field registry."""
    return MappingProxyType(
        {module.PLATFORM: module.entry(field_registry) for module in _INSTALLED}
    )


PLATFORMS: Mapping[PlatformType, PlatformEntry] = build_platforms(
    FieldHandlerRegistry(BUILTIN_FIELDS)
)
"""The installed Platforms with no Host extension fields.

Each built app holds its own table, ``build_platforms(builder.field_registry)``,
on ``app.state.platforms``; the keys are always the same installed set.
"""


def platform_messenger(
    messenger: IMessenger,
    platforms: Mapping[PlatformType, PlatformEntry] | None = None,
) -> IMessenger | None:
    """The Platform Messenger for ``messenger``'s Platform, or ``None``.

    Looks the Platform up in ``platforms`` (the app's table; ``PLATFORMS``
    when omitted) and lets its entry extend the given Messenger. ``None`` when
    the Platform is not in the table or adds no Platform Messenger.
    """
    entry = (platforms if platforms is not None else PLATFORMS).get(messenger.platform)
    if entry is None or entry.build_platform_messenger is None:
        return None
    return entry.build_platform_messenger(messenger)


__all__ = [
    "BUILTIN_FIELDS",
    "PLATFORMS",
    "MessengerBuilder",
    "MessengerDeps",
    "PlatformEntry",
    "PlatformMessengerBuilder",
    "build_platforms",
    "platform_messenger",
]
