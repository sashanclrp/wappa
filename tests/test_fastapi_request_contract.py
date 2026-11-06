"""Multipart request behavior across FastAPI upgrades."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wappa.api.dependencies.media_transfer import get_media_uploader
from wappa.api.routes.media import upload_router
from wappa.domain.models.media_result import MediaUploadResult


@pytest.fixture
def upload_api() -> tuple[TestClient, AsyncMock]:
    handler = AsyncMock()
    handler.upload_media_from_bytes.return_value = MediaUploadResult(
        success=True, media_id="media-1"
    )
    app = FastAPI()
    app.include_router(upload_router, prefix="/api/whatsapp")
    app.dependency_overrides[get_media_uploader] = lambda: handler
    return TestClient(app), handler


@pytest.mark.parametrize("media_type", [None, "", "image/png"])
def test_upload_optional_form_field_uses_file_type_unless_overridden(
    upload_api: tuple[TestClient, AsyncMock], media_type: str | None
) -> None:
    client, handler = upload_api
    response = client.post(
        "/api/whatsapp/media/upload",
        files={"file": ("photo.jpg", b"photo", "image/jpeg")},
        data={} if media_type is None else {"media_type": media_type},
    )
    assert response.status_code == 200
    assert response.json()["media_id"] == "media-1"
    handler.upload_media_from_bytes.assert_awaited_once_with(
        file_data=b"photo", media_type=media_type or "image/jpeg", filename="photo.jpg"
    )


def test_upload_missing_file_remains_a_request_validation_error(
    upload_api: tuple[TestClient, AsyncMock],
) -> None:
    client, handler = upload_api
    response = client.post(
        "/api/whatsapp/media/upload", data={"media_type": "image/jpeg"}
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "file"]
    handler.upload_media_from_bytes.assert_not_awaited()
