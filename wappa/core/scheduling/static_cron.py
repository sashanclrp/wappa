"""Built-in static crons as a trigger source of the scheduled lane."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from wappa.core.scheduling.dispatch import Scheduling
from wappa.domain.events.scheduled_event import SOURCE_STATIC_CRON, ScheduledEvent
from wappa.domain.inbox.identity import InboxRef

if TYPE_CHECKING:
    import fastapi_crons
    from fastapi import FastAPI


@dataclass(frozen=True)
class StaticCron:
    """One cron declared on ``SchedulingPlugin.add_cron``."""

    action: str
    expr: str
    inbox_ref: InboxRef | None = None
    user_id: str | None = None
    tags: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    max_retries: int = 0
    retry_delay: float = 5.0
    timeout: int = 120

    def to_event(self) -> ScheduledEvent:
        return ScheduledEvent(
            action=self.action,
            source=SOURCE_STATIC_CRON,
            inbox_ref=self.inbox_ref,
            user_id=self.user_id,
            # A firing must not see what an earlier firing did to its payload.
            payload=copy.deepcopy(self.payload),
            metadata={"cron_expr": self.expr, "tags": list(self.tags)},
        )


def register_static_cron(
    crons: fastapi_crons.Crons, cron: StaticCron, app: FastAPI
) -> None:
    """Register ``cron`` with the engine; failures reach its retry policy."""

    @crons.cron(
        expr=cron.expr,
        name=cron.action,
        tags=cron.tags,
        max_retries=cron.max_retries,
        retry_delay=cron.retry_delay,
        timeout=cron.timeout,
    )
    async def _fire() -> None:
        await Scheduling.from_app(app).dispatch(cron.to_event())
