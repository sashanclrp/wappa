"""An Instagram rejection logs Meta's error fields; the result stays credential-free."""

from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import SecretStr

from wappa.domain.results import OperationOutcome
from wappa.messaging.instagram import graph


@pytest.mark.asyncio
async def test_rejection_logs_metas_error_fields(monkeypatch) -> None:
    body = {
        "error": {
            "message": "(#100) Unsupported image format",
            "type": "OAuthException",
            "code": 100,
            "error_subcode": 2018047,
            "fbtrace_id": "Abc",
            "unexpected": "dropped",
        }
    }
    transport = httpx.MockTransport(lambda _req: httpx.Response(400, json=body))
    log = MagicMock()
    monkeypatch.setattr(graph, "logger", log)

    async with httpx.AsyncClient(transport=transport) as client:
        result = await graph.graph_request(
            client,
            "https://graph.facebook.com/v26.0",
            "me/messages",
            SecretStr("EAAsecret"),
            method="POST",
            operation="send image",
        )

    assert result.outcome is OperationOutcome.REJECTED
    assert result.error_code == "100/2018047"
    assert "Unsupported image format" not in (result.error or "")
    _fmt, operation, status, summary = log.error.call_args.args
    assert (operation, status) == ("send image", 400)
    assert summary["message"] == "(#100) Unsupported image format"
    assert summary["error_subcode"] == 2018047
    assert "unexpected" not in summary
    assert "EAAsecret" not in str(log.error.call_args)
