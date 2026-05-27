"""Regression tests: API event dispatch submits through BackgroundWorkTracker."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from wappa.core.lifecycle import BackgroundWorkTracker
from wappa.messaging.whatsapp.models.basic_models import MessageResult


def _fake_app_state(tracker: BackgroundWorkTracker) -> SimpleNamespace:
    return SimpleNamespace(background_work_tracker=tracker)


def _fake_request(tracker: BackgroundWorkTracker) -> MagicMock:
    req = MagicMock()
    req.app.state = _fake_app_state(tracker)
    return req


def _dummy_result() -> MessageResult:
    return MessageResult(
        success=True,
        message_id="wamid.test123",
        error=None,
    )


class TestDispatchApiMessageEvent:
    @pytest.mark.asyncio
    async def test_uses_tracker(self):
        from wappa.api.dependencies.event_dependencies import (
            dispatch_api_message_event,
        )

        tracker = BackgroundWorkTracker()
        request = _fake_request(tracker)
        dispatcher = AsyncMock()

        await dispatch_api_message_event(
            dispatcher=dispatcher,
            message_type="text",
            result=_dummy_result(),
            request_payload={"body": "hi"},
            recipient="5511999999999",
            request=request,
        )

        assert tracker.active_count >= 0
        await tracker.drain(timeout=2.0)
        dispatcher.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_without_tracker(self):
        from wappa.api.dependencies.event_dependencies import (
            dispatch_api_message_event,
        )

        request = MagicMock()
        request.app.state = SimpleNamespace()

        with pytest.raises(RuntimeError, match="BackgroundWorkTracker not available"):
            await dispatch_api_message_event(
                dispatcher=AsyncMock(),
                message_type="text",
                result=_dummy_result(),
                request_payload={},
                recipient="5511999999999",
                request=request,
            )

    @pytest.mark.asyncio
    async def test_skips_during_drain(self):
        from wappa.api.dependencies.event_dependencies import (
            dispatch_api_message_event,
        )

        tracker = BackgroundWorkTracker()
        tracker.begin_drain()
        request = _fake_request(tracker)

        await dispatch_api_message_event(
            dispatcher=AsyncMock(),
            message_type="text",
            result=_dummy_result(),
            request_payload={},
            recipient="5511999999999",
            request=request,
        )
        assert tracker.active_count == 0


class TestFireApiEvent:
    @pytest.mark.asyncio
    async def test_uses_tracker(self):
        from wappa.api.utils.event_decorators import fire_api_event

        tracker = BackgroundWorkTracker()
        request = _fake_request(tracker)
        dispatcher = AsyncMock()

        fire_api_event(
            dispatcher=dispatcher,
            message_type="text",
            result=_dummy_result(),
            request_payload={"body": "hi"},
            recipient="5511999999999",
            fastapi_request=request,
        )

        assert tracker.active_count == 1
        await tracker.drain(timeout=2.0)

    def test_raises_without_tracker(self):
        from wappa.api.utils.event_decorators import fire_api_event

        request = MagicMock()
        request.app.state = SimpleNamespace()

        with pytest.raises(RuntimeError, match="BackgroundWorkTracker not available"):
            fire_api_event(
                dispatcher=AsyncMock(),
                message_type="text",
                result=_dummy_result(),
                request_payload={},
                recipient="5511999999999",
                fastapi_request=request,
            )

    def test_skips_during_drain(self):
        from wappa.api.utils.event_decorators import fire_api_event

        tracker = BackgroundWorkTracker()
        tracker.begin_drain()
        request = _fake_request(tracker)

        fire_api_event(
            dispatcher=AsyncMock(),
            message_type="text",
            result=_dummy_result(),
            request_payload={},
            recipient="5511999999999",
            fastapi_request=request,
        )
        assert tracker.active_count == 0


class TestDispatchMessageEventDecorator:
    @pytest.mark.asyncio
    async def test_decorator_uses_tracker(self):
        from wappa.api.utils.event_decorators import dispatch_message_event

        tracker = BackgroundWorkTracker()
        dispatcher = AsyncMock()
        req = _fake_request(tracker)

        pydantic_model = MagicMock()
        pydantic_model.model_dump.return_value = {"body": "hi"}
        pydantic_model.recipient = "5511999999999"
        pydantic_model.user_id = None

        @dispatch_message_event("text")
        async def handler(
            request=None, api_dispatcher=None, fastapi_request=None
        ) -> MessageResult:
            return _dummy_result()

        await handler(
            request=pydantic_model,
            api_dispatcher=dispatcher,
            fastapi_request=req,
        )
        assert tracker.active_count >= 0
        await tracker.drain(timeout=2.0)
        dispatcher.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_decorator_raises_without_tracker(self):
        from wappa.api.utils.event_decorators import dispatch_message_event

        req = MagicMock()
        req.app.state = SimpleNamespace()

        pydantic_model = MagicMock()
        pydantic_model.model_dump.return_value = {}
        pydantic_model.recipient = "5511999999999"
        pydantic_model.user_id = None

        @dispatch_message_event("text")
        async def handler(
            request=None, api_dispatcher=None, fastapi_request=None
        ) -> MessageResult:
            return _dummy_result()

        with pytest.raises(RuntimeError, match="BackgroundWorkTracker not available"):
            await handler(
                request=pydantic_model,
                api_dispatcher=AsyncMock(),
                fastapi_request=req,
            )
