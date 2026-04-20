import logging

import aiohttp
import pytest

from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient


class FakeResponse:
    def __init__(
        self,
        *,
        status: int,
        body: str,
        reason: str = "Bad Request",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self._body = body
        self.reason = reason
        self.headers = headers or {}
        self.request_info = None
        self.history = ()

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def text(self) -> str:
        return self._body

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=self.request_info,
                history=self.history,
                status=self.status,
                message=self.reason,
                headers=self.headers,
            )


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self._response = response

    def post(self, *args, **kwargs) -> FakeResponse:
        return self._response


@pytest.mark.asyncio
async def test_post_request_logs_meta_error_details_and_masks_token(caplog) -> None:
    error_body = (
        '{"error":{"message":"(#100) Invalid parameter",'
        '"type":"OAuthException","code":100,'
        '"error_data":{"details":"Unexpected key \\"recipient\\" on param."},'
        '"fbtrace_id":"A1B2C3"}}'
    )
    client = WhatsAppClient(
        session=FakeSession(FakeResponse(status=400, body=error_body)),
        access_token="1234567890abcdefghijklmnopqrstuvwxyz",
        phone_number_id="493419253863068",
        logger=logging.getLogger("tests.whatsapp_client"),
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(aiohttp.ClientResponseError):
        await client.post_request(
            {
                "messaging_product": "whatsapp",
                "type": "text",
                "text": {"body": "Welcome to Wappa", "preview_url": False},
                "recipient": "CO.2186878922080769",
            }
        )

    assert "Meta raw response" in caplog.text
    assert "Unexpected key \\\"recipient\\\" on param." in caplog.text
    assert "Meta error summary" in caplog.text
    assert "Bearer 12345678...wxyz" in caplog.text
    assert "1234567890abcdefghijklmnopqrstuvwxyz" not in caplog.text
