"""WhatsApp Template sends as a focused capability (ADR-0016).

Templates are a WhatsApp business-initiated message family with no equivalent
on other Platforms, so they are not ``IMessenger`` methods. Reach them with
``messenger.require_capability(ITemplateMessaging)``. Through a
``MessengerPipeline`` the capability still runs the message middleware chain
under the method names ``send_text_template`` / ``send_media_template`` /
``send_location_template``. Hosts that resolve Templates per Inbox use
``OutboundRuntime`` / ``InboxTemplateTransport``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from wappa.domain.interfaces.messaging_interface import (
    TemplateAuthenticationMethodValue,
    TemplateBodyParameters,
    TemplateRoutingPolicyValue,
)
from wappa.domain.messaging_targets import DirectMessage

if TYPE_CHECKING:
    from wappa.domain.results import MessageResult


class ITemplateMessaging(ABC):
    """Approved-Template sends bound to one Inbox."""

    @abstractmethod
    async def send_text_template(
        self,
        template_name: str,
        target: DirectMessage,
        body_parameters: TemplateBodyParameters = None,
        language_code: str = "es",
        *,
        template_type: str,
        routing_policy: TemplateRoutingPolicyValue = "category_default",
        authentication_method: TemplateAuthenticationMethodValue = None,
        authentication_button_index: int = 0,
    ) -> MessageResult: ...

    @abstractmethod
    async def send_media_template(
        self,
        template_name: str,
        target: DirectMessage,
        media_type: str,
        media_id: str | None = None,
        media_url: str | None = None,
        body_parameters: TemplateBodyParameters = None,
        language_code: str = "es",
        *,
        template_type: str,
        routing_policy: TemplateRoutingPolicyValue = "category_default",
    ) -> MessageResult: ...

    @abstractmethod
    async def send_location_template(
        self,
        template_name: str,
        target: DirectMessage,
        latitude: str,
        longitude: str,
        name: str,
        address: str,
        body_parameters: TemplateBodyParameters = None,
        language_code: str = "es",
        *,
        template_type: str,
        routing_policy: TemplateRoutingPolicyValue = "category_default",
    ) -> MessageResult: ...


TEMPLATE_METHODS = frozenset(
    {"send_text_template", "send_media_template", "send_location_template"}
)

__all__ = ["TEMPLATE_METHODS", "ITemplateMessaging"]
