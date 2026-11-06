"""Send invocation value, middleware protocol and chain binding."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from ....domain.messaging_targets import MessageTarget

if TYPE_CHECKING:
    from wappa.domain.results import MessageResult


# Canonical priority bands. Middleware registers with a numeric priority;
# these names exist only for documentation and tests.
PRIORITY_RELIABILITY: int = 10
PRIORITY_NOTIFICATIONS: int = 30
PRIORITY_CACHE: int = 50
PRIORITY_LIFECYCLE: int = 70
PRIORITY_OBSERVABILITY: int = 90


@dataclass(frozen=True, slots=True)
class SendInvocation:
    """Structured view of one outbound call travelling through the pipeline.

    Middleware reads ``method_name``, ``message_type``, ``target`` for
    routing decisions and ``arguments`` for the named payload. The
    invocation is immutable; middleware that needs to rewrite arguments
    constructs a new invocation via :meth:`with_arguments` before calling
    ``call_next``.

    - ``args``/``kwargs`` are what the raw messenger method receives
      (positional + keyword). The pipeline calls
      ``getattr(raw, method_name)(*args, **kwargs)``.
    - ``arguments`` is the same information keyed by parameter name, used
      for event emission and logging. It is canonical for middleware that
      serialize or inspect payloads.
    """

    method_name: str
    message_type: str
    target: MessageTarget
    args: tuple[Any, ...]
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    arguments: Mapping[str, Any] = field(default_factory=dict)

    @property
    def recipient(self) -> str:
        """Native address evidence for middleware; sending uses target.

        A DirectMessage yields its recipient ID; a PrivateReply yields
        ``comment:<comment_id>`` because the User is not yet addressable.
        """
        return self.target.address

    def with_arguments(
        self,
        arguments: Mapping[str, Any],
        *,
        args: tuple[Any, ...] | None = None,
        kwargs: Mapping[str, Any] | None = None,
    ) -> SendInvocation:
        """Return a copy with substituted arguments (for middleware rewrites).

        If ``args``/``kwargs`` are not supplied, they default to the values
        in ``arguments`` (in insertion order for ``args``). Callers that
        need a different positional shape pass both explicitly.
        """
        resolved_args = args if args is not None else tuple(arguments.values())
        resolved_kwargs = kwargs if kwargs is not None else {}
        return SendInvocation(
            method_name=self.method_name,
            message_type=self.message_type,
            target=self.target,
            args=resolved_args,
            kwargs=resolved_kwargs,
            arguments=arguments,
        )

    def to_request_payload(self) -> dict[str, Any]:
        """Serializable named-argument payload (for event emission)."""
        return cast(dict[str, Any], _to_serializable(dict(self.arguments)))


SendNext = Callable[[SendInvocation], Awaitable["MessageResult"]]


@runtime_checkable
class MessengerMiddleware(Protocol):
    """Cross-cutting concern around an outbound :class:`IMessenger` call.

    Implementations receive the captured :class:`SendInvocation` plus a
    ``call_next`` callable. They may do work before and/or after awaiting
    ``call_next``, short-circuit by returning without calling it, or
    rewrite the invocation and forward it.

    Middleware is app-scoped (constructed once at ``WappaBuilder.build``);
    per-request identity comes from ContextVars (see
    ``wappa.core.sse.context.SSEEventContext``).
    """

    name: str

    async def handle(
        self,
        invocation: SendInvocation,
        call_next: SendNext,
    ) -> MessageResult: ...


# (middleware, priority) — priority is stored alongside the middleware so
# the builder owns ordering, not the middleware itself.
MiddlewareEntry = tuple[MessengerMiddleware, int]


def _bind(mw: MessengerMiddleware, call_next: SendNext) -> SendNext:
    """Bind a middleware to the inner `call_next`, producing a new `call_next`."""

    async def invoke(invocation: SendInvocation) -> MessageResult:
        return await mw.handle(invocation, call_next)

    return invoke


def _to_serializable(value: Any) -> Any:
    """Coerce arbitrary values (Path, Pydantic models, containers) to JSON-safe."""
    if isinstance(value, Path):
        return str(value)

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=False)

    if isinstance(value, dict):
        return {str(key): _to_serializable(item) for key, item in value.items()}

    if isinstance(value, list | tuple | set):
        return [_to_serializable(item) for item in value]

    return value
