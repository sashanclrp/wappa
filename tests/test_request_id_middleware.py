"""Tests for request correlation IDs on responses, logs, and context cleanup."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wappa.api.middleware import DEFAULT_REQUEST_ID_HEADER, RequestIdMiddleware
from wappa.core.logging.context import get_current_request_id
from wappa.core.logging.logger import WappaJSONFormatter


def _app(**middleware_kwargs) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware, **middleware_kwargs)

    @app.get("/echo")
    async def echo() -> dict[str, str | None]:
        return {"request_id": get_current_request_id()}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("handler exploded")

    return app


def test_response_carries_a_generated_request_id() -> None:
    with TestClient(_app()) as client:
        response = client.get("/echo")

    request_id = response.headers[DEFAULT_REQUEST_ID_HEADER]
    assert request_id
    assert response.json()["request_id"] == request_id


def test_each_request_gets_a_distinct_id() -> None:
    with TestClient(_app()) as client:
        first = client.get("/echo").headers[DEFAULT_REQUEST_ID_HEADER]
        second = client.get("/echo").headers[DEFAULT_REQUEST_ID_HEADER]

    assert first != second


def test_inbound_request_id_is_propagated_across_hops() -> None:
    with TestClient(_app()) as client:
        response = client.get("/echo", headers={DEFAULT_REQUEST_ID_HEADER: "trace-123"})

    assert response.headers[DEFAULT_REQUEST_ID_HEADER] == "trace-123"
    assert response.json()["request_id"] == "trace-123"


def test_inbound_id_is_ignored_when_the_edge_is_untrusted() -> None:
    with TestClient(_app(trust_inbound=False)) as client:
        response = client.get("/echo", headers={DEFAULT_REQUEST_ID_HEADER: "spoofed"})

    assert response.headers[DEFAULT_REQUEST_ID_HEADER] != "spoofed"


@pytest.mark.parametrize("inbound", ["", "   ", "x" * 200])
def test_unusable_inbound_ids_fall_back_to_a_generated_one(inbound: str) -> None:
    with TestClient(_app()) as client:
        response = client.get("/echo", headers={DEFAULT_REQUEST_ID_HEADER: inbound})

    request_id = response.headers[DEFAULT_REQUEST_ID_HEADER]
    assert request_id
    assert request_id != inbound.strip()


def test_custom_header_name_is_honoured() -> None:
    with TestClient(_app(header_name="X-Correlation-Id")) as client:
        response = client.get("/echo", headers={"X-Correlation-Id": "corr-1"})

    assert response.headers["X-Correlation-Id"] == "corr-1"
    assert DEFAULT_REQUEST_ID_HEADER not in response.headers


def test_context_is_cleared_after_the_response() -> None:
    with TestClient(_app()) as client:
        client.get("/echo")

    assert get_current_request_id() is None


def test_context_is_cleared_even_when_the_handler_raises() -> None:
    client = TestClient(_app(), raise_server_exceptions=False)
    with client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert get_current_request_id() is None


def test_json_logs_carry_the_active_request_id() -> None:
    records: list[str] = []
    formatter = WappaJSONFormatter()

    app = _app()

    @app.get("/logged")
    async def logged() -> dict[str, str]:
        record = logging.LogRecord(
            name="wappa.test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="processing webhook",
            args=(),
            exc_info=None,
        )
        records.append(formatter.format(record))
        return {"status": "ok"}

    with TestClient(app) as client:
        response = client.get("/logged", headers={DEFAULT_REQUEST_ID_HEADER: "trace-9"})

    assert json.loads(records[0])["request_id"] == "trace-9"
    assert response.headers[DEFAULT_REQUEST_ID_HEADER] == "trace-9"


def test_built_wappa_app_stamps_request_ids_on_health_responses() -> None:
    # RequestIdMiddleware is wired by WappaCorePlugin, so a default app gets
    # correlation IDs without the host adding any middleware.
    from wappa.core.factory.wappa_builder import WappaBuilder
    from wappa.core.plugins.wappa_core_plugin import WappaCorePlugin

    app = WappaBuilder().add_plugin(WappaCorePlugin()).build()

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.headers[DEFAULT_REQUEST_ID_HEADER]


def test_json_logs_omit_request_id_outside_a_request() -> None:
    formatter = WappaJSONFormatter()
    record = logging.LogRecord(
        name="wappa.test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="background work",
        args=(),
        exc_info=None,
    )

    assert "request_id" not in json.loads(formatter.format(record))
