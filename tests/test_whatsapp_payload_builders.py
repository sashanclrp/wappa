from wappa.messaging.whatsapp.payloads import (
    WhatsAppMediaPayloadBuilder,
    WhatsAppMessagePayloadBuilder,
)


def test_whatsapp_message_payloads_uses_to_for_phone_recipient() -> None:
    builder = WhatsAppMessagePayloadBuilder()

    payload = builder.create_text_message(
        text="hola",
        recipient="+57 300 123 4567",
    )

    assert payload["to"] == "+573001234567"
    assert "recipient" not in payload


def test_whatsapp_message_payloads_uses_recipient_for_bsuid() -> None:
    builder = WhatsAppMessagePayloadBuilder()

    payload = builder.create_text_message(
        text="hola",
        recipient="co.13491208655302741918",
    )

    assert payload["recipient"] == "CO.13491208655302741918"
    assert "to" not in payload


def test_whatsapp_media_payloads_uses_recipient_for_bsuid() -> None:
    builder = WhatsAppMediaPayloadBuilder()

    payload = builder.create_image_message(
        media_reference="media-id",
        recipient="co.13491208655302741918",
    )

    assert payload["recipient"] == "CO.13491208655302741918"
    assert "to" not in payload


def test_whatsapp_media_payloads_reports_document_caption_support() -> None:
    builder = WhatsAppMediaPayloadBuilder()

    limits = builder.get_media_limits()

    assert limits["caption_support"]["document"] is True
