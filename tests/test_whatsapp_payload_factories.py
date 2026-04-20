from wappa.domain.factories.media_factory import WhatsAppMediaFactory
from wappa.domain.factories.message_factory import WhatsAppMessageFactory


def test_whatsapp_message_factory_uses_to_for_phone_recipient() -> None:
    factory = WhatsAppMessageFactory()

    payload = factory.create_text_message(
        text="hola",
        recipient="+57 300 123 4567",
    )

    assert payload["to"] == "+573001234567"
    assert "recipient" not in payload


def test_whatsapp_message_factory_uses_recipient_for_bsuid() -> None:
    factory = WhatsAppMessageFactory()

    payload = factory.create_text_message(
        text="hola",
        recipient="co.13491208655302741918",
    )

    assert payload["recipient"] == "CO.13491208655302741918"
    assert "to" not in payload


def test_whatsapp_media_factory_uses_recipient_for_bsuid() -> None:
    factory = WhatsAppMediaFactory()

    payload = factory.create_image_message(
        media_reference="media-id",
        recipient="co.13491208655302741918",
    )

    assert payload["recipient"] == "CO.13491208655302741918"
    assert "to" not in payload


def test_whatsapp_media_factory_reports_document_caption_support() -> None:
    factory = WhatsAppMediaFactory()

    limits = factory.get_media_limits()

    assert limits["caption_support"]["document"] is True
