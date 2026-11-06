"""Template transport capability bound to one Inbox."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import monotonic
from typing import TYPE_CHECKING

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interfaces.session_provider import (
    HTTPSessionClosedError,
    RuntimeDrainingError,
)
from wappa.domain.interfaces.template_messaging import ITemplateMessaging

from .dispatch import (
    _failure_result,
    _normalize_result,
    _request_digest,
    _send_request,
    resolve_template_route,
)
from .requests import TemplateTransportRequest
from .result import TemplateTransportResult
from .values import TemplateTransportOutcome

if TYPE_CHECKING:
    from wappa.domain.interfaces.messaging_interface import IMessenger


class InboxTemplateTransport:
    """Template transport capability bound to one Inbox."""

    def __init__(
        self,
        *,
        inbox_ref: InboxRef,
        messenger_provider: Callable[[], Awaitable[IMessenger]],
    ) -> None:
        self.inbox_ref = inbox_ref
        # Builds this Inbox's Messenger (with app middleware) on each send;
        # ``OutboundRuntime.templates`` binds it to ``OutboundRuntime.messenger``.
        self._messenger_provider = messenger_provider

    @property
    def inbox_id(self) -> str:
        return self.inbox_ref.inbox_id

    async def send(self, request: TemplateTransportRequest) -> TemplateTransportResult:
        digest = _request_digest(request)
        started = monotonic()
        endpoint, routing_reason = resolve_template_route(
            request.category, request.routing.policy
        )

        def failure(
            outcome: TemplateTransportOutcome, code: str, message: str
        ) -> TemplateTransportResult:
            return _failure_result(
                outcome=outcome,
                inbox_id=self.inbox_id,
                digest=digest,
                started=started,
                request=request,
                endpoint=endpoint,
                routing_reason=routing_reason,
                code=code,
                message=message,
            )

        try:
            messenger = await self._messenger_provider()
        except (RuntimeDrainingError, HTTPSessionClosedError):
            return failure(
                TemplateTransportOutcome.TRANSPORT_UNAVAILABLE,
                "runtime_unavailable",
                "The outbound runtime is not accepting new transport calls.",
            )
        except Exception:
            return failure(
                TemplateTransportOutcome.TRANSPORT_UNAVAILABLE,
                "transport_unavailable",
                "The Inbox transport could not be prepared.",
            )

        if messenger.capability(ITemplateMessaging) is None:
            # Nothing was sent, so the outcome is a proven rejection.
            return failure(
                TemplateTransportOutcome.REJECTED,
                "capability_unsupported",
                f"{messenger.platform.value} does not provide Template messaging.",
            )

        try:
            result = await _send_request(messenger, request)
        except (RuntimeDrainingError, HTTPSessionClosedError):
            return failure(
                TemplateTransportOutcome.TRANSPORT_UNAVAILABLE,
                "runtime_unavailable",
                "The outbound runtime is not accepting new transport calls.",
            )
        except ValueError:
            return failure(
                TemplateTransportOutcome.REJECTED,
                "invalid_template_request",
                "The Template request is invalid for this platform.",
            )
        except Exception:
            return failure(
                TemplateTransportOutcome.INDETERMINATE,
                "INDETERMINATE",
                "The platform outcome could not be determined.",
            )
        return _normalize_result(
            result,
            inbox_id=self.inbox_id,
            digest=digest,
            started=started,
            request=request,
            endpoint=endpoint,
            routing_reason=routing_reason,
        )
