"""Tests for ExternalEventRegistry handler subscription and dispatch."""

from __future__ import annotations

import pytest

from wappa import ExternalEvent, ExternalEventRegistry


def _event(event_type: str, source: str = "mercadopago") -> ExternalEvent:
    return ExternalEvent(source=source, event_type=event_type, inbox_id="inbox-1")


@pytest.mark.asyncio
async def test_exact_subscription_receives_its_event() -> None:
    registry = ExternalEventRegistry()
    seen: list[str] = []

    @registry.on("mercadopago", "payment.approved")
    async def handler(event: ExternalEvent) -> None:
        seen.append(event.event_type)

    report = await registry.dispatch(_event("payment.approved"))

    assert seen == ["payment.approved"]
    assert (report.matched, report.succeeded, report.failed) == (1, 1, 0)


@pytest.mark.asyncio
async def test_unrelated_event_types_and_sources_are_not_dispatched() -> None:
    registry = ExternalEventRegistry()
    seen: list[str] = []

    @registry.on("mercadopago", "payment.approved")
    async def handler(event: ExternalEvent) -> None:
        seen.append(event.event_type)

    assert (await registry.dispatch(_event("payment.rejected"))).matched == 0
    assert (
        await registry.dispatch(_event("payment.approved", source="stripe"))
    ).matched == 0
    assert seen == []


@pytest.mark.asyncio
async def test_multiple_handlers_subscribe_to_the_same_event_type() -> None:
    registry = ExternalEventRegistry()
    calls: list[str] = []

    @registry.on("stripe", "invoice.paid")
    async def audit(event: ExternalEvent) -> None:
        calls.append("audit")

    @registry.on("stripe", "invoice.paid")
    async def notify(event: ExternalEvent) -> None:
        calls.append("notify")

    report = await registry.dispatch(_event("invoice.paid", source="stripe"))

    assert calls == ["audit", "notify"]  # registration order
    assert report.succeeded == 2


@pytest.mark.asyncio
async def test_wildcard_and_prefix_subscriptions_run_after_exact_matches() -> None:
    registry = ExternalEventRegistry()
    calls: list[str] = []

    @registry.on("stripe")
    async def catch_all(event: ExternalEvent) -> None:
        calls.append("all")

    @registry.on("stripe", "invoice.*")
    async def invoices(event: ExternalEvent) -> None:
        calls.append("prefix")

    @registry.on("stripe", "invoice.paid")
    async def paid(event: ExternalEvent) -> None:
        calls.append("exact")

    await registry.dispatch(_event("invoice.paid", source="stripe"))

    assert calls == ["exact", "prefix", "all"]


@pytest.mark.asyncio
async def test_prefix_subscription_matches_deeper_event_types() -> None:
    registry = ExternalEventRegistry()
    calls: list[str] = []

    @registry.on("crm", "contact.*")
    async def contacts(event: ExternalEvent) -> None:
        calls.append(event.event_type)

    await registry.dispatch(_event("contact.created.v2", source="crm"))
    await registry.dispatch(_event("deal.created", source="crm"))

    assert calls == ["contact.created.v2"]


@pytest.mark.asyncio
async def test_handler_matching_several_tiers_runs_once() -> None:
    registry = ExternalEventRegistry()
    calls: list[str] = []

    async def handler(event: ExternalEvent) -> None:
        calls.append(event.event_type)

    registry.register("stripe", "invoice.paid", handler)
    registry.register("stripe", "invoice.*", handler)
    registry.register("stripe", "*", handler)

    report = await registry.dispatch(_event("invoice.paid", source="stripe"))

    assert calls == ["invoice.paid"]
    assert report.matched == 1


@pytest.mark.asyncio
async def test_failing_handler_does_not_stop_the_others() -> None:
    registry = ExternalEventRegistry()
    calls: list[str] = []

    @registry.on("stripe", "invoice.paid")
    async def broken(event: ExternalEvent) -> None:
        calls.append("broken")
        raise RuntimeError("downstream is down")

    @registry.on("stripe", "invoice.paid")
    async def healthy(event: ExternalEvent) -> None:
        calls.append("healthy")

    report = await registry.dispatch(_event("invoice.paid", source="stripe"))

    assert calls == ["broken", "healthy"]
    assert report.matched == 2
    assert report.succeeded == 1
    assert report.failed == 1
    assert report.errors[0][0].endswith("broken")
    assert isinstance(report.errors[0][1], RuntimeError)


@pytest.mark.asyncio
async def test_dispatch_without_subscribers_is_a_no_op() -> None:
    registry = ExternalEventRegistry()
    report = await registry.dispatch(_event("payment.approved"))

    assert (report.matched, report.succeeded, report.failed) == (0, 0, 0)


def test_handlers_for_reports_the_dispatch_order() -> None:
    registry = ExternalEventRegistry()

    async def exact(event: ExternalEvent) -> None: ...

    async def catch_all(event: ExternalEvent) -> None: ...

    registry.register("stripe", "*", catch_all)
    registry.register("stripe", "invoice.paid", exact)

    assert registry.handlers_for("stripe", "invoice.paid") == [exact, catch_all]
    assert registry.handlers_for("stripe", "charge.failed") == [catch_all]
    assert registry.handlers_for("other", "invoice.paid") == []


def test_sync_handlers_are_rejected_at_registration() -> None:
    registry = ExternalEventRegistry()

    def sync_handler(event: ExternalEvent) -> None: ...

    with pytest.raises(ValueError, match="async"):
        registry.register("stripe", "invoice.paid", sync_handler)


@pytest.mark.parametrize(("source", "event_type"), [("", "x"), ("stripe", " ")])
def test_blank_subscription_keys_are_rejected(source: str, event_type: str) -> None:
    registry = ExternalEventRegistry()

    async def handler(event: ExternalEvent) -> None: ...

    with pytest.raises(ValueError):
        registry.register(source, event_type, handler)
