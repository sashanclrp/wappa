"""One hook for every Scheduled Task, whichever engine fired it."""

from dataclasses import dataclass

from wappa import ScheduledEvent, WappaEventHandler
from wappa.domain.messaging_targets import DeliveryAddresses, DirectMessage
from wappa.webhooks import InboundMessageWebhook


@dataclass(frozen=True)
class ReminderDependencies:
    """Stands in for a Host's typed services, built once per invocation."""

    last_reminder_key: str = "last_reminder_id"


class MasterEventHandler(WappaEventHandler):
    """Routes Scheduled Tasks; Wappa has already prepared this clone's context."""

    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        """This example only runs Scheduled Tasks."""

    async def process_scheduled_event(self, event: ScheduledEvent) -> None:
        # Build typed Host dependencies once, here, then route by action. The
        # handler is a fresh clone, so nothing here reaches another invocation.
        self.dependencies = ReminderDependencies()

        match event.action:
            case "appointment_reminder":
                await self._send_reminder(event)
            case "weekly_report" | "campaign_report":
                await self._send_report(event)
            case "heartbeat":
                self.logger.info(f"Heartbeat from {event.source}: {event.execution_id}")
            case _:
                # Raising reaches the scheduler, which applies its own policy.
                raise ValueError(f"Unknown scheduled action: {event.action}")

    async def _send_reminder(self, event: ScheduledEvent) -> None:
        assert self.messenger is not None
        assert self.cache_factory is not None
        assert self.inbox_ref is not None
        assert self.user_id is not None

        await self.messenger.send_text(
            target=DirectMessage(
                inbox_ref=self.inbox_ref,
                addresses=DeliveryAddresses.of(self.user_id),
            ),
            text=f"Reminder: {event.payload['text']}",
        )
        await self.cache_factory.create_user_cache().upsert(
            {self.dependencies.last_reminder_key: event.execution_id}
        )

    async def _send_report(self, event: ScheduledEvent) -> None:
        assert self.messenger is not None
        assert self.inbox_ref is not None

        # The Host owns recipients. self.scope prepares each one's context,
        # including its canonical User, without building anything by hand.
        for owner in event.payload["owners"]:
            async with self.scope(user_id=owner) as scoped:
                assert scoped.user_id is not None
                await self.messenger.send_text(
                    target=DirectMessage(
                        inbox_ref=self.inbox_ref,
                        addresses=DeliveryAddresses.of(scoped.user_id),
                    ),
                    text=f"Your {event.action.replace('_', ' ')} is ready",
                )
