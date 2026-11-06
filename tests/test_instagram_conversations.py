"""Instagram conversation contracts: families, lanes, sends, comments, reads.

Fixtures follow Meta's Instagram webhook examples (Graph v26.0, fetched
2026-11-03) with synthetic IDs. They are offline evidence only.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel, SecretStr

from wappa import WappaEventHandler
from wappa.api.routes.webhooks import create_webhook_router
from wappa.core.config.meta_application import MetaApplicationConfig
from wappa.core.events import WappaEventDispatcher
from wappa.core.events.field_registry import FieldHandlerRegistry
from wappa.core.inbound import MetaCallbackAuthenticator
from wappa.core.inbound.instagram_routing import route_instagram_payload
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle
from wappa.domain.inbox import InboxRef, PlatformAccountRef
from wappa.domain.inbox.errors import InboxNotFoundError
from wappa.domain.inbox.ports import IInboxCredentialResolver, ResolvedInboxCredentials
from wappa.messaging import (
    CardMedia,
    CommentRef,
    ContactCard,
    DeliveryAddresses,
    DirectMessage,
    ICommentControls,
    IConversationContentReader,
    InteractiveHeader,
    ListRow,
    ListSection,
    MessageCard,
    MessengerPipeline,
    OperationOutcome,
    PostRef,
    PrivateReply,
    ReadOutcome,
    ReplyButton,
    TargetInboxMismatchError,
    UnsupportedOperationError,
)
from wappa.messaging.instagram.media import InstagramAttachmentReader
from wappa.messaging.instagram.media_library import InstagramMediaLibrary
from wappa.messaging.instagram.messenger import InstagramMessenger
from wappa.platforms import BUILTIN_FIELDS, build_platforms
from wappa.processors.instagram_processor import InstagramWebhookProcessor
from wappa.schemas.core.types import MessageType, PlatformType
from wappa.webhooks import (
    CustomWebhook,
    EchoOrigin,
    EntryPointKind,
    InboundMessageWebhook,
    IncomingCommentWebhook,
    MentionSubject,
    MentionWebhook,
    MessageUpdateKind,
    MessageUpdateWebhook,
    OutboundEchoWebhook,
    SystemEventType,
    SystemWebhook,
)

SECRET = SecretStr("test-meta-secret")
ACCOUNT = "17890001"
USER = "12345"
REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=ACCOUNT)
OTHER_REF = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id="17890999")
CDN = "https://lookaside.fbsbx.com/ig_messaging_cdn/?asset_id=1&signature=s"


def messaging(*events, account=ACCOUNT):
    return {
        "object": "instagram",
        "entry": [{"id": account, "messaging": list(events)}],
    }


def changes(*items, account=ACCOUNT):
    return {
        "object": "instagram",
        "entry": [{"id": account, "time": 1793710000, "changes": list(items)}],
    }


def msg(user=USER, **parts):
    return {
        "sender": {"id": user},
        "recipient": {"id": ACCOUNT},
        "timestamp": 1793710000123,
        **parts,
    }


async def parse(payload):
    return await InstagramWebhookProcessor().translate(payload)


# ── inbound families ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("attachment", "message_type", "class_name"),
    [
        (
            {"type": "image", "payload": {"url": CDN}},
            MessageType.IMAGE,
            "InstagramImageMessage",
        ),
        (
            {"type": "video", "payload": {"url": CDN}},
            MessageType.VIDEO,
            "InstagramVideoMessage",
        ),
        (
            {"type": "audio", "payload": {"url": CDN}},
            MessageType.AUDIO,
            "InstagramAudioMessage",
        ),
        (
            {"type": "file", "payload": {"url": CDN}},
            MessageType.DOCUMENT,
            "InstagramFileMessage",
        ),
        (
            {
                "type": "ig_post",
                "payload": {"ig_post_media_id": "1813", "title": "cap", "url": CDN},
            },
            MessageType.SHARE,
            "InstagramShareMessage",
        ),
        (
            {"type": "ig_reel", "payload": {"url": CDN}},
            MessageType.SHARE,
            "InstagramShareMessage",
        ),
        (
            {"type": "story_mention", "payload": {"url": CDN}},
            MessageType.STORY_MENTION,
            "InstagramShareMessage",
        ),
    ],
)
async def test_attachment_families_become_typed_messages(
    attachment, message_type, class_name
):
    parsed = await parse(
        messaging(msg(message={"mid": "m1", "attachments": [attachment]}))
    )
    assert isinstance(parsed, InboundMessageWebhook)
    assert parsed.message.message_type is message_type
    assert type(parsed.message).__name__ == class_name
    assert parsed.message.url == attachment["payload"]["url"]
    assert parsed.user.user_id == USER and parsed.user.phone_number == ""
    assert parsed.message.get_download_info()["requires_platform_auth"] is False


async def test_shared_post_keeps_provider_media_id_and_multi_attachments():
    parsed = await parse(
        messaging(
            msg(
                message={
                    "mid": "m1",
                    "attachments": [
                        {
                            "type": "ig_post",
                            "payload": {"ig_post_media_id": "1813", "url": CDN},
                        },
                    ],
                }
            )
        )
    )
    assert parsed.message.shared_media_id == "1813"
    many = await parse(
        messaging(
            msg(
                message={
                    "mid": "m2",
                    "attachments": [
                        {"type": "image", "payload": {"url": CDN + "a"}},
                        {"type": "image", "payload": {"url": CDN + "b"}},
                    ],
                }
            )
        )
    )
    assert many.message.urls == (CDN + "a", CDN + "b")


async def test_story_reply_and_message_reply_context():
    story = await parse(
        messaging(
            msg(
                message={
                    "mid": "m1",
                    "text": "love it",
                    "reply_to": {"story": {"id": "st1", "url": CDN}},
                }
            )
        )
    )
    assert story.message.message_type is MessageType.TEXT
    assert (
        story.message.context.is_story_reply and story.message.context.story_id == "st1"
    )
    reply = await parse(
        messaging(msg(message={"mid": "m2", "text": "yes", "reply_to": {"mid": "m0"}}))
    )
    assert reply.message.get_reply_context() == ("m0", None)


async def test_quick_reply_is_one_message_with_selection_evidence():
    parsed = await parse(
        messaging(
            msg(
                message={
                    "mid": "m1",
                    "text": "Yes",
                    "quick_reply": {"payload": "form:yes"},
                }
            )
        )
    )
    assert isinstance(parsed, InboundMessageWebhook)
    assert parsed.get_interactive_selection() == "form:yes"
    assert parsed.get_message_text() == "Yes"


async def test_postback_is_a_button_reply_message_like_whatsapp():
    parsed = await parse(
        messaging(
            msg(postback={"mid": "pb1", "title": "Start", "payload": "form:start"})
        )
    )
    assert isinstance(parsed, InboundMessageWebhook)
    assert parsed.get_interactive_selection() == "form:start"
    assert parsed.get_message_text() == "Start"
    assert parsed.message.is_button_reply and parsed.message.message_id == "pb1"


async def test_edit_and_delete_are_message_updates():
    edit = await parse(
        messaging(msg(message_edit={"mid": "m1", "text": "fixed", "num_edit": 1}))
    )
    assert isinstance(edit, MessageUpdateWebhook)
    assert edit.update_kind is MessageUpdateKind.EDITED and edit.text == "fixed"
    deleted = await parse(messaging(msg(message={"mid": "m1", "is_deleted": True})))
    assert isinstance(deleted, MessageUpdateWebhook) and deleted.text is None
    assert deleted.is_deletion


async def test_referrals_reactions_and_echoes_never_trigger_messages():
    standalone = await parse(
        messaging(
            msg(referral={"ref": "promo", "source": "IGME", "type": "OPEN_THREAD"})
        )
    )
    assert isinstance(standalone, SystemWebhook)
    assert standalone.system_event_type is SystemEventType.REFERRAL
    assert standalone.event_detail.entry_referral.kind is EntryPointKind.LINK
    assert standalone.event_detail.entry_referral.ref == "promo"
    assert standalone.event_detail.platform_event is None  # typed, no dict
    attached = await parse(
        messaging(
            msg(
                message={
                    "mid": "m1",
                    "text": "hi",
                    "referral": {
                        "ad_id": "ad1",
                        "source": "ADS",
                        "type": "OPEN_THREAD",
                    },
                }
            )
        )
    )
    assert isinstance(attached, InboundMessageWebhook)
    assert attached.entry_referral.ad_id == "ad1"
    assert attached.entry_referral.kind is EntryPointKind.AD
    reaction = await parse(
        messaging(
            msg(
                reaction={
                    "mid": "m1",
                    "action": "react",
                    "reaction": "love",
                    "emoji": "❤️",
                }
            )
        )
    )
    assert isinstance(reaction, InboundMessageWebhook)
    assert reaction.message.message_type is MessageType.REACTION
    assert reaction.message.target_message_id == "m1"
    assert reaction.message.emoji == "❤️" and not reaction.message.is_removal
    unreact = await parse(messaging(msg(reaction={"mid": "m1", "action": "unreact"})))
    assert unreact.message.is_removal and unreact.message.emoji == ""
    echo = await parse(
        messaging(
            {
                "sender": {"id": ACCOUNT},
                "recipient": {"id": USER},
                "timestamp": 1793710000123,
                "message": {
                    "mid": "e1",
                    "attachments": [{"type": "image", "payload": {"url": CDN}}],
                    "is_echo": True,
                },
            }
        )
    )
    assert isinstance(echo, OutboundEchoWebhook)
    assert echo.origin is EchoOrigin.UNKNOWN  # the runtime proves it
    assert echo.user.user_id == USER
    assert echo.message_id == "e1" and echo.native_type == "image"
    assert echo.message is not None and echo.message.sender_id == ACCOUNT
    assert echo.message_type is MessageType.IMAGE


@pytest.mark.parametrize("field", ["comments", "live_comments"])
async def test_comments_keep_source_parent_author_and_media(field):
    parsed = await parse(
        changes(
            {
                "field": field,
                "value": {
                    "from": {"id": "igsid-9", "username": "ana"},
                    "comment_id": "c2",
                    "parent_id": "c1",
                    "text": "price?",
                    "media": {
                        "id": "media-1",
                        "media_product_type": "REELS",
                        "ad_id": "ad9",
                    },
                },
            }
        )
    )
    assert isinstance(parsed, IncomingCommentWebhook)
    assert parsed.source.value == field and parsed.is_live is (field == "live_comments")
    assert parsed.comment_ref == CommentRef(inbox_ref=REF, comment_id="c2")
    assert parsed.parent_comment_ref.comment_id == "c1" and parsed.is_reply is True
    assert parsed.post_ref.media_id == "media-1" and parsed.ad_id == "ad9"
    assert parsed.author.username == "ana" and not parsed.is_own_comment


async def test_comment_without_parent_evidence_is_unknown_and_id_alias():
    parsed = await parse(
        changes(
            {
                "field": "comments",
                "value": {"id": "c3", "text": "hi", "from": {"id": ACCOUNT}},
            }
        )
    )
    assert parsed.comment_id == "c3"
    assert parsed.is_reply is None and parsed.post_ref is None
    assert parsed.is_own_comment


async def test_mentions_distinguish_media_and_comment_subjects():
    media = await parse(changes({"field": "mentions", "value": {"media_id": "m9"}}))
    assert isinstance(media, MentionWebhook)
    assert media.subject is MentionSubject.MEDIA and media.comment_ref is None
    comment = await parse(
        changes({"field": "mentions", "value": {"media_id": "m9", "comment_id": "c9"}})
    )
    assert comment.subject is MentionSubject.COMMENT
    assert comment.comment_ref.comment_id == "c9"


class StoryInsight(BaseModel):
    media_id: str
    impressions: int


async def test_extension_field_registration_and_unknown_change():
    registry = FieldHandlerRegistry(BUILTIN_FIELDS)

    async def handler(webhook):
        return None

    registry.register(
        "story_insights",
        parser=StoryInsight,
        handler=handler,
        platform=PlatformType.INSTAGRAM,
    )
    with pytest.raises(ValueError, match="built-in"):
        registry.register(
            "comments",
            parser=StoryInsight,
            handler=handler,
            platform=PlatformType.INSTAGRAM,
        )
    # WhatsApp membership unaffected
    assert registry.get("story_insights", PlatformType.WHATSAPP) is None
    processor = InstagramWebhookProcessor(registry)
    custom = await processor.translate(
        changes(
            {"field": "story_insights", "value": {"media_id": "s1", "impressions": 3}}
        )
    )
    assert isinstance(custom, CustomWebhook) and custom.parsed.impressions == 3
    unknown = await processor.translate(
        changes({"field": "something_new", "value": {"x": 1}})
    )
    assert unknown.system_event_type is SystemEventType.UNSUPPORTED_EVENT


# ── admission and dispatch ──────────────────────────────────────────────


class Resolver(IInboxCredentialResolver):
    def __init__(self, accounts=(ACCOUNT,)):
        self.accounts = set(accounts)
        self.calls = []

    async def resolve_credentials(self, ref):
        self.calls.append(ref)
        if ref.inbox_id not in self.accounts:
            raise InboxNotFoundError(ref)
        return ResolvedInboxCredentials(
            inbox_ref=ref,
            account_ref=PlatformAccountRef(
                platform=ref.platform, platform_account_id=ref.inbox_id
            ),
            access_token=SecretStr(f"token-{ref.inbox_id}"),
            credential_version=1,
        )

    async def list_inbox_refs_for_platform_account(self, ref):
        return ()


async def test_mixed_batch_routes_each_event_and_change_once():
    batch = {
        "object": "instagram",
        "entry": [
            {
                "id": ACCOUNT,
                "time": 1793710000,
                "messaging": [msg(message={"mid": "m1", "text": "hi"})],
                "changes": [
                    {"field": "comments", "value": {"id": "c1", "text": "x"}},
                    {"field": "mentions", "value": {"media_id": "m9"}},
                ],
            }
        ],
    }
    deliveries = await route_instagram_payload(batch, Resolver())
    assert len(deliveries) == 3
    assert all(d.inbox_ref == REF for d in deliveries)


class Recorder(WappaEventHandler):
    def __init__(self):
        super().__init__()
        self.events = []

    async def process_message(self, webhook):
        self.events.append(("message", webhook.user.user_id, self.inbox_id))

    async def process_message_update(self, webhook):
        self.events.append(("update", webhook.update_kind.value, self.inbox_id))

    async def process_comment(self, webhook):
        self.events.append(("comment", webhook.comment_id, self.inbox_id))

    async def process_mention(self, webhook):
        self.events.append(("mention", webhook.subject.value, self.inbox_id))

    async def process_status(self, webhook):
        self.events.append(("status", webhook.status.value, self.inbox_id))


def _app(handler, resolver, registry=None):
    app = FastAPI()
    app.include_router(
        create_webhook_router(WappaEventDispatcher(handler, field_registry=registry))
    )
    app.state.meta_application_config = MetaApplicationConfig(
        app_secret=SECRET, whatsapp_webhook_verify_token=SecretStr("verify")
    )
    app.state.inbox_runtime = SimpleNamespace(credential_resolver=resolver)
    app.state.background_work_tracker = BackgroundWorkTracker()
    app.state.messenger_middleware = []
    app.state.wappa_cache_type = "memory"
    app.state.platforms = build_platforms(
        registry or FieldHandlerRegistry(BUILTIN_FIELDS)
    )
    return app


async def _post(app, payload, *, sign=True):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(500))
    ) as provider:
        app.state.session_lifecycle = SessionLifecycle(provider)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://t"
        ) as client:
            body = json.dumps(payload).encode()
            headers = (
                {"X-Hub-Signature-256": MetaCallbackAuthenticator(SECRET).sign(body)}
                if sign
                else {}
            )
            response = await client.post(
                "/webhook/inboxes/instagram", content=body, headers=headers
            )
            await app.state.background_work_tracker.drain()
        await app.state.session_lifecycle.close()
    return response


async def test_signed_mixed_batch_dispatches_every_lane_exactly_once():
    handler = Recorder()
    resolver = Resolver(accounts=(ACCOUNT, OTHER_REF.inbox_id))
    batch = {
        "object": "instagram",
        "entry": [
            {
                "id": ACCOUNT,
                "messaging": [
                    msg(
                        message={
                            "mid": "q1",
                            "text": "Yes",
                            "quick_reply": {"payload": "p"},
                        }
                    ),
                    msg(postback={"mid": "pb", "title": "Go", "payload": "go"}),
                    msg(message_edit={"mid": "m1", "text": "x", "num_edit": 1}),
                    msg(read={"mid": "out1"}),
                ],
            },
            {
                "id": OTHER_REF.inbox_id,
                "time": 1793710000,
                "changes": [
                    {
                        "field": "comments",
                        "value": {"id": "c1", "text": "x", "from": {"id": "u9"}},
                    },
                    {
                        "field": "mentions",
                        "value": {"media_id": "m9", "comment_id": "c9"},
                    },
                ],
            },
        ],
    }
    response = await _post(_app(handler, resolver), batch)
    assert response.status_code == 200, response.text
    assert sorted(handler.events) == sorted(
        [
            ("message", USER, ACCOUNT),
            ("message", USER, ACCOUNT),
            ("update", "edited", ACCOUNT),
            ("status", "read", ACCOUNT),
            ("comment", "c1", OTHER_REF.inbox_id),
            ("mention", "comment", OTHER_REF.inbox_id),
        ]
    )


async def test_unsigned_or_unknown_account_batches_schedule_nothing():
    handler = Recorder()
    resolver = Resolver()
    batch = changes({"field": "comments", "value": {"id": "c1"}})
    unsigned = await _post(_app(handler, resolver), batch, sign=False)
    assert unsigned.status_code == 401 and resolver.calls == []
    mixed = {
        "object": "instagram",
        "entry": [
            {"id": ACCOUNT, "messaging": [msg(message={"mid": "m1", "text": "hi"})]},
            {
                "id": "unknown-account",
                "changes": [{"field": "comments", "value": {"id": "c1"}}],
            },
        ],
    }
    rejected = await _post(_app(handler, resolver), mixed)
    assert rejected.status_code == 400 and handler.events == []


async def test_extension_parse_failure_rejects_whole_batch():
    handler = Recorder()
    registry = FieldHandlerRegistry(BUILTIN_FIELDS)
    seen = []

    async def on_insight(webhook):
        seen.append(webhook)

    registry.register(
        "story_insights",
        parser=StoryInsight,
        handler=on_insight,
        platform=PlatformType.INSTAGRAM,
    )
    batch = {
        "object": "instagram",
        "entry": [
            {
                "id": ACCOUNT,
                "messaging": [msg(message={"mid": "m1", "text": "hi"})],
            },
            {
                "id": ACCOUNT,
                "changes": [{"field": "story_insights", "value": {"media_id": "s"}}],
            },
        ],
    }
    response = await _post(_app(handler, Resolver(), registry), batch)
    assert response.status_code == 400
    assert handler.events == [] and seen == []
    good = changes(
        {"field": "story_insights", "value": {"media_id": "s", "impressions": 2}}
    )
    ok = await _post(_app(handler, Resolver(), registry), good)
    assert ok.status_code == 200 and seen[0].parsed.impressions == 2


# ── outbound operations ─────────────────────────────────────────────────


def _messenger(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    messenger = InstagramMessenger(
        inbox_ref=REF,
        access_token=SecretStr("tkn"),
        session_provider=lambda: client,
        graph_api_version="v26.0",
        graph_base_url="https://graph.facebook.com",
    )
    return messenger, client


def _ok(sent):
    def handler(request):
        sent.append(request)
        if request.url.path.endswith("/replies"):
            return httpx.Response(200, json={"id": "reply-1"})
        if request.url.path.endswith("/message_attachments"):
            return httpx.Response(200, json={"attachment_id": "att-1"})
        body = (
            json.loads(request.content)
            if request.content
            and request.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        if "sender_action" in body:
            return httpx.Response(200, json={"recipient_id": USER})
        return httpx.Response(200, json={"recipient_id": USER, "message_id": "out.mid"})

    return handler


DM = DirectMessage(inbox_ref=REF, addresses=DeliveryAddresses.of(USER))


async def test_every_dm_operation_uses_native_wire_format():
    sent = []
    messenger, client = _messenger(_ok(sent))
    async with client:
        pipeline = MessengerPipeline(messenger)
        assert (
            await pipeline.send_image(CDN, target=DM, reply_to_message_id="m0")
        ).success
        assert (await pipeline.send_audio(CDN, target=DM)).success
        assert (await pipeline.send_video(CDN, target=DM)).success
        assert (await pipeline.send_document(CDN, target=DM)).success
        assert (
            await pipeline.send_list_message(
                [
                    ListSection(
                        title="Menu",
                        rows=[
                            ListRow(id="a", title="A", description="dropped"),
                            ListRow(id="b", title="B"),
                        ],
                    )
                ],
                DM,
                "Pick",
                "Open",
                header="Head",
                footer="Foot",
            )
        ).success
        assert (
            await pipeline.send_button_message(
                [ReplyButton(id="go", title="Go")], DM, "Next?", footer="Tap"
            )
        ).success
        assert (
            await pipeline.send_carousel(
                [
                    MessageCard(
                        title="One",
                        subtitle="s",
                        header=CardMedia.image(url="https://example.com/1.png"),
                        buttons=(ReplyButton(id="1", title="Pick"),),
                    ),
                    MessageCard(title="Two", default_url="https://example.com/2"),
                ],
                DM,
                "Our picks",
            )
        ).success
        assert (
            await pipeline.send_cta_message("Open", "https://example.com", DM, "Body")
        ).success
        assert (
            await pipeline.send_button_message(
                [ReplyButton(id="ok", title="OK")],
                DM,
                "Buttons body",
                header=InteractiveHeader.of_image(url="https://example.com/c.png"),
                footer="Footer",
            )
        ).success
        assert (await pipeline.mark_as_read("m9", typing=True, target=DM)).success
    bodies = [json.loads(r.content) for r in sent]
    assert bodies[0]["message"]["attachment"] == {
        "type": "image",
        "payload": {"url": CDN},
    }
    assert bodies[0]["reply_to"] == {"mid": "m0"}
    assert bodies[3]["message"]["attachment"]["type"] == "file"
    assert bodies[4]["message"]["text"] == "Head\n\nPick\n\nFoot"
    assert bodies[4]["message"]["quick_replies"][0] == {
        "content_type": "text",
        "title": "A",
        "payload": "a",
    }
    template = bodies[5]["message"]["attachment"]["payload"]
    assert template["template_type"] == "button" and template["text"] == "Next?\n\nTap"
    assert template["buttons"] == [{"type": "postback", "title": "Go", "payload": "go"}]
    assert bodies[6]["message"] == {"text": "Our picks"}
    elements = bodies[7]["message"]["attachment"]["payload"]["elements"]
    assert elements[0]["buttons"][0]["type"] == "postback"
    assert elements[1]["default_action"]["url"] == "https://example.com/2"
    assert (
        bodies[8]["message"]["attachment"]["payload"]["buttons"][0]["type"] == "web_url"
    )
    # A media header goes first as its own attachment, then the buttons.
    assert bodies[9]["message"]["attachment"] == {
        "type": "image",
        "payload": {"url": "https://example.com/c.png"},
    }
    buttons = bodies[10]["message"]["attachment"]["payload"]
    assert buttons["template_type"] == "button"
    assert buttons["text"] == "Buttons body\n\nFooter"
    assert bodies[11] == {"recipient": {"id": USER}, "sender_action": "mark_seen"}
    assert bodies[12]["sender_action"] == "typing_on"
    assert all(r.headers["Authorization"] == "Bearer tkn" for r in sent)


async def test_local_file_is_uploaded_then_sent_by_attachment_id(tmp_path: Path):
    sent = []
    pdf = tmp_path / "menu.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    messenger, client = _messenger(_ok(sent))
    async with client:
        result = await messenger.send_document(pdf, DM)
    assert result.success
    assert sent[0].url.path == f"/v26.0/{ACCOUNT}/message_attachments"
    assert b'name="filedata"' in sent[0].content and b"platform" in sent[0].content
    assert json.loads(sent[1].content)["message"]["attachment"] == {
        "type": "file",
        "payload": {"attachment_id": "att-1"},
    }
    with pytest.raises(ValueError, match="supports"):
        await messenger.send_image(pdf, DM)


async def test_private_reply_public_reply_and_target_rules():
    sent = []
    messenger, client = _messenger(_ok(sent))
    comment = CommentRef(inbox_ref=REF, comment_id="c1")
    async with client:
        private = await messenger.send_text(
            "Thanks! DM sent", target=PrivateReply(comment_ref=comment)
        )
        controls = messenger.require_capability(ICommentControls)
        public = await controls.reply_comment(comment, "Thanks for commenting")
        with pytest.raises(UnsupportedOperationError):
            await messenger.send_image(CDN, target=PrivateReply(comment_ref=comment))
        with pytest.raises(UnsupportedOperationError):
            await messenger.send_text(
                "x", target=PrivateReply(comment_ref=comment), reply_to_message_id="m"
            )
        with pytest.raises(ValueError, match="different Inbox"):
            await messenger.send_text(
                "x",
                target=PrivateReply(
                    comment_ref=CommentRef(inbox_ref=OTHER_REF, comment_id="c")
                ),
            )
        with pytest.raises(ValueError, match="different Inbox"):
            await controls.reply_comment(
                CommentRef(inbox_ref=OTHER_REF, comment_id="c"), "x"
            )
    assert json.loads(sent[0].content)["recipient"] == {"comment_id": "c1"}
    assert private.success and private.recipient == USER
    assert sent[1].url.path == "/v26.0/c1/replies"
    assert (
        public.outcome is OperationOutcome.ACCEPTED and public.comment_id == "reply-1"
    )
    assert public.parent_comment_id == "c1"
    assert len(sent) == 2


async def test_private_reply_is_platform_neutral_and_rejected_at_send():
    """Constructing a PrivateReply names no Platform; an adapter without
    comment-addressed replies rejects it when sending."""
    reply = PrivateReply(
        comment_ref=CommentRef(inbox_ref=InboxRef.whatsapp("pnid"), comment_id="c")
    )
    assert reply.inbox_ref == InboxRef.whatsapp("pnid")
    posted: list = []

    class Client:
        async def post_request(self, payload):
            posted.append(payload)
            return {"success": True}

    from wappa.messaging.whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger

    wa = WhatsAppMessenger(
        client=Client(),  # type: ignore[arg-type]
        media_handler=None,  # type: ignore[arg-type]
        interactive_handler=None,  # type: ignore[arg-type]
        template_handler=None,  # type: ignore[arg-type]
        specialized_handler=None,  # type: ignore[arg-type]
        inbox_id="pnid",
    )
    with pytest.raises(UnsupportedOperationError, match="PrivateReply"):
        await wa.send_text("hi", reply)
    assert posted == []


async def test_local_limits_reject_before_io():
    sent = []
    messenger, client = _messenger(_ok(sent))
    async with client:
        first = [ListRow(id=f"a{i}", title=str(i)) for i in range(6)]
        second = [ListRow(id=f"b{i}", title=str(i)) for i in range(6)]
        with pytest.raises(ValueError, match="10 rows in total"):
            await messenger.send_list_message(
                [
                    ListSection(title="a", rows=first),
                    ListSection(title="b", rows=second),
                ],
                DM,
                "x",
                "Open",
            )
        with pytest.raises(ValueError):
            await messenger.send_button_message(
                [ReplyButton(id=str(i), title=str(i)) for i in range(4)], DM, "x"
            )
        with pytest.raises(ValueError, match="2–10 cards"):
            await messenger.send_carousel(
                [MessageCard(title="t", subtitle="s")] * 11, DM, "x"
            )
        with pytest.raises(ValueError, match="2–10 cards"):
            await messenger.send_carousel(
                [MessageCard(title="t", subtitle="s")], DM, "x"
            )
        with pytest.raises(ValueError, match="need a subtitle"):
            await messenger.send_carousel([MessageCard(title="only")] * 2, DM, "x")
        with pytest.raises(ValueError, match="https"):
            await messenger.send_image("http://insecure.example/a.png", DM)
    assert sent == []
    assert {
        "send_button_message",
        "send_list_message",
        "send_carousel",
        "mark_as_read",
    } <= messenger.supported_operations
    assert not {"mark_seen", "set_typing", "send_quick_replies"} & set(
        messenger.supported_operations
    )


@pytest.mark.parametrize(
    ("response", "outcome", "code"),
    [
        (
            httpx.Response(400, json={"error": {"code": 10, "error_subcode": 2534022}}),
            "rejected",
            "10/2534022",
        ),
        (
            httpx.Response(503, json={"error": {"code": 2}}),
            "indeterminate",
            "INDETERMINATE",
        ),
        (
            httpx.Response(200, json={"recipient_id": USER}),
            "indeterminate",
            "INDETERMINATE",
        ),
    ],
)
async def test_send_outcomes_are_honest_and_never_retried(response, outcome, code):
    calls = []

    def handler(request):
        calls.append(request)
        return response

    messenger, client = _messenger(handler)
    async with client:
        result = await messenger.send_image(CDN, DM)
    assert not result.success and result.error_code == code and len(calls) == 1
    assert "tkn" not in (result.error or "")
    if outcome == "rejected":
        assert "window" in result.error


async def test_transport_failure_is_indeterminate():
    def handler(request):
        raise httpx.ConnectTimeout("boom", request=request)

    messenger, client = _messenger(handler)
    async with client:
        result = await messenger.send_button_message(
            [ReplyButton(id="a", title="a")], DM, "x"
        )
        reply = await messenger.require_capability(ICommentControls).reply_comment(
            CommentRef(inbox_ref=REF, comment_id="c1"), "x"
        )
    assert result.error_code == "INDETERMINATE"
    assert reply.outcome is OperationOutcome.INDETERMINATE and reply.comment_id is None


# ── comment controls and content reads ──────────────────────────────────


async def test_comment_controls_native_calls_and_outcomes():
    sent = []

    def handler(request):
        sent.append(request)
        if request.url.path.endswith("/c-bad"):
            return httpx.Response(200, json={"success": False})
        return httpx.Response(200, json={"success": True})

    messenger, client = _messenger(handler)
    controls = MessengerPipeline(messenger).require_capability(ICommentControls)
    comment = CommentRef(inbox_ref=REF, comment_id="c1")
    async with client:
        assert (await controls.hide_comment(comment)).success
        assert (await controls.unhide_comment(comment)).success
        assert (await controls.delete_comment(comment)).success
        disabled = await controls.set_comments_enabled(
            PostRef(inbox_ref=REF, media_id="m1"), False
        )
        odd = await controls.hide_comment(CommentRef(inbox_ref=REF, comment_id="c-bad"))
        with pytest.raises(ValueError, match="different Inbox"):
            await controls.delete_comment(
                CommentRef(inbox_ref=OTHER_REF, comment_id="c1")
            )
    assert [(r.method, r.url.path, dict(r.url.params)) for r in sent[:4]] == [
        ("POST", "/v26.0/c1", {"hide": "true"}),
        ("POST", "/v26.0/c1", {"hide": "false"}),
        ("DELETE", "/v26.0/c1", {}),
        ("POST", "/v26.0/m1", {"comment_enabled": "false"}),
    ]
    assert disabled.operation.value == "disable_comments"
    assert odd.outcome is OperationOutcome.INDETERMINATE
    assert len(sent) == 5


async def test_content_reader_post_comments_pagination_and_failures():
    def handler(request):
        path = request.url.path
        if path == "/v26.0/m1":
            return httpx.Response(
                200,
                json={
                    "id": "m1",
                    "caption": "New drop",
                    "media_type": "CAROUSEL_ALBUM",
                    "permalink": "https://instagram.com/p/x",
                    "timestamp": "2026-11-03T10:00:00+0000",
                    "children": {
                        "data": [{"id": "ch1", "media_type": "IMAGE", "media_url": CDN}]
                    },
                },
            )
        if path == "/v26.0/m1/comments":
            after = request.url.params.get("after")
            if after:
                return httpx.Response(
                    200, json={"data": [{"id": "c3", "text": "last"}]}
                )
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "c1",
                            "text": "hi",
                            "from": {"id": "u1", "username": "ana"},
                        }
                    ],
                    "paging": {"cursors": {"after": "CUR"}, "next": "https://next"},
                },
            )
        if path == "/v26.0/gone":
            return httpx.Response(
                400, json={"error": {"code": 100, "error_subcode": 33}}
            )
        if path == "/v26.0/private":
            return httpx.Response(403, json={"error": {"code": 10}})
        return httpx.Response(500)

    messenger, client = _messenger(handler)
    reader = messenger.require_capability(IConversationContentReader)
    async with client:
        post = await reader.get_post(PostRef(inbox_ref=REF, media_id="m1"))
        first = await reader.list_comments(
            PostRef(inbox_ref=REF, media_id="m1"), limit=1
        )
        second = await reader.list_comments(
            PostRef(inbox_ref=REF, media_id="m1"), after=first.value.next_cursor
        )
        gone = await reader.get_post(PostRef(inbox_ref=REF, media_id="gone"))
        private = await reader.get_comment(
            CommentRef(inbox_ref=REF, comment_id="private")
        )
        down = await reader.get_comment(CommentRef(inbox_ref=REF, comment_id="down"))
    assert (
        post.found
        and post.value.caption == "New drop"
        and post.value.children[0].media_id == "ch1"
    )
    assert post.value.timestamp.year == 2026 and post.value.like_count is None
    assert (
        first.value.items[0].author_username == "ana"
        and first.value.next_cursor == "CUR"
    )
    assert (
        second.value.items[0].comment_ref.comment_id == "c3"
        and not second.value.has_more
    )
    assert gone.outcome is ReadOutcome.NOT_FOUND
    assert private.outcome is ReadOutcome.ACCESS_DENIED
    assert down.outcome is ReadOutcome.UNAVAILABLE


async def test_processor_performs_no_network_io(monkeypatch):
    def forbid(*args, **kwargs):
        raise AssertionError("processor attempted network I/O")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbid)
    parsed = await parse(
        changes({"field": "comments", "value": {"id": "c1", "media": {"id": "m1"}}})
    )
    assert parsed.post_ref.media_id == "m1"


# ── attachment bytes ────────────────────────────────────────────────────


async def test_attachment_reader_is_bounded_and_credential_free():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.host == "lookaside.fbsbx.com" and "redirect" in str(request.url):
            return httpx.Response(302, headers={"location": "https://evil.example/x"})
        if "expired" in str(request.url):
            return httpx.Response(404)
        if "big" in str(request.url):
            return httpx.Response(200, content=b"x" * 2048)
        return httpx.Response(
            200, content=b"\x89PNG data", headers={"content-type": "image/png"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        reader = InstagramAttachmentReader(lambda: client)
        ok = await reader.get_bytes(CDN)
        third_party = await reader.get_bytes("https://evil.example/a.png")
        redirected = await reader.get_bytes(CDN + "&redirect=1")
        expired = await reader.get_bytes(CDN + "&expired=1")
        library = InstagramMediaLibrary(None, reader)  # type: ignore[arg-type]
        big = await library.download(CDN + "&big=1", max_bytes=1024)
        default = await library.download(CDN + "&big=1")
    assert ok.found and ok.value.content_type == "image/png" and ok.value.size == 9
    assert third_party.outcome is ReadOutcome.REJECTED
    assert redirected.outcome is ReadOutcome.REJECTED
    assert expired.outcome is ReadOutcome.NOT_FOUND
    assert big.outcome is ReadOutcome.REJECTED and big.error_code == "SIZE"
    assert default.found and default.value.size == 2048
    assert all("authorization" not in r.headers for r in seen)
    assert all(r.url.host != "evil.example" for r in seen)


async def test_whatsapp_rejects_private_reply_explicitly():
    from wappa.messaging.whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger

    wa = WhatsAppMessenger.__new__(WhatsAppMessenger)
    wa._inbox_id = "555"
    with pytest.raises(UnsupportedOperationError):
        await wa.send_text(
            "x",
            target=PrivateReply(comment_ref=CommentRef(inbox_ref=REF, comment_id="c")),
        )


async def test_pipeline_exposes_private_reply_address_to_middleware():
    seen = []

    class Spy:
        name = "spy"

        async def handle(self, invocation, call_next):
            seen.append(invocation.recipient)
            return await call_next(invocation)

    sent = []
    messenger, client = _messenger(_ok(sent))
    async with client:
        pipeline = MessengerPipeline(messenger, middleware=[(Spy(), 50)])
        await pipeline.send_text(
            "hi",
            target=PrivateReply(comment_ref=CommentRef(inbox_ref=REF, comment_id="c1")),
        )
        await pipeline.send_button_message([ReplyButton(id="a", title="a")], DM, "x")
    assert seen == ["comment:c1", USER]


async def test_mark_as_read_is_seen_then_typing_on_one_contract():
    sent: list = []
    messenger, client = _messenger(_ok(sent))
    async with client:
        read = await messenger.mark_as_read("m1", typing=True, target=DM)
        plain = await messenger.mark_as_read("m2", target=DM)
    assert read.success and plain.success
    assert read.message_id == "m1" and read.recipient == USER
    actions = [json.loads(r.content)["sender_action"] for r in sent]
    assert actions == ["mark_seen", "typing_on", "mark_seen"]
    assert "mark_as_read" in messenger.supported_operations


async def test_mark_as_read_skips_typing_when_seen_is_refused():
    sent: list = []

    def refuse(request):
        sent.append(request)
        return httpx.Response(
            400, json={"error": {"message": "nope", "code": 10, "error_subcode": 2018}}
        )

    messenger, client = _messenger(refuse)
    async with client:
        result = await messenger.mark_as_read("m1", typing=True, target=DM)
    assert not result.success and result.error_code
    assert len(sent) == 1  # no typing_on after a refused seen


async def test_mark_as_read_rejects_a_target_from_another_inbox():
    messenger, client = _messenger(_ok([]))
    other = DirectMessage(inbox_ref=OTHER_REF, addresses=DeliveryAddresses.of(USER))
    async with client:
        with pytest.raises(TargetInboxMismatchError):
            await messenger.mark_as_read("m1", target=other)


async def test_whatsapp_mark_as_read_sends_typing_and_accepts_a_target():
    from wappa.messaging.whatsapp.messenger.whatsapp_messenger import (
        WhatsAppMessenger,
    )

    posted: list[dict] = []

    class Client:
        async def post_request(self, payload):
            posted.append(payload)
            return {"success": True}

    wa = WhatsAppMessenger(
        client=Client(),  # type: ignore[arg-type]
        media_handler=None,  # type: ignore[arg-type]
        interactive_handler=None,  # type: ignore[arg-type]
        template_handler=None,  # type: ignore[arg-type]
        specialized_handler=None,  # type: ignore[arg-type]
        inbox_id="pnid",
    )
    wa_dm = DirectMessage(
        inbox_ref=InboxRef.whatsapp("pnid"), addresses=DeliveryAddresses.of("573001")
    )
    assert (await wa.mark_as_read("wamid.1", typing=True, target=wa_dm)).success
    assert posted[0]["typing_indicator"] == {"type": "text"}
    assert (await wa.mark_as_read("wamid.2", wa_dm)).success
    assert "typing_indicator" not in posted[1]
    with pytest.raises(TargetInboxMismatchError):
        await wa.mark_as_read("wamid.3", target=DM)


async def test_caption_becomes_a_follow_up_text_and_filename_is_presentation():
    sent: list = []
    messenger, client = _messenger(_ok(sent))
    async with client:
        image = await messenger.send_image(CDN, DM, caption="Our menu")
        doc = await messenger.send_document(CDN, DM, filename="menu.pdf")
    assert image.success and doc.success
    bodies = [json.loads(r.content) for r in sent]
    assert bodies[0]["message"]["attachment"]["type"] == "image"
    assert bodies[1]["message"] == {"text": "Our menu"}
    assert bodies[2]["message"]["attachment"]["type"] == "file"
    assert len(bodies) == 3


async def test_location_contact_and_sticker_are_adapted_requests_are_not():
    sent: list = []
    messenger, client = _messenger(_ok(sent))
    async with client:
        loc = await messenger.send_location(
            4.6, -74.08, DM, name="Mimeia", address="Bogotá"
        )
        contact = await messenger.send_contact(
            ContactCard.model_validate(
                {
                    "name": {"formatted_name": "Ana Ruiz"},
                    "phones": [{"phone": "+573001112233"}],
                    "emails": [{"email": "ana@example.com"}],
                }
            ),
            DM,
        )
        # Both renditions: Instagram picks the png, WhatsApp would pick the webp.
        sticker = await messenger.send_sticker(
            ["https://example.com/s.webp", "https://example.com/s.png"], DM
        )
        with pytest.raises(ValueError, match="png"):
            await messenger.send_sticker("https://example.com/s.webp", DM)
        with pytest.raises(UnsupportedOperationError):
            await messenger.send_location_request("Where are you?", DM)
        with pytest.raises(UnsupportedOperationError):
            await messenger.send_contact_request("Share your phone", DM)
    assert loc.success and contact.success and sticker.success
    bodies = [json.loads(r.content) for r in sent]
    assert bodies[0]["message"]["text"] == (
        "Mimeia\nBogotá\n📍 https://www.google.com/maps/search/?api=1&query=4.6,-74.08"
    )
    assert bodies[1]["message"]["text"] == (
        "👤 Ana Ruiz\n📞 +573001112233\n✉️ ana@example.com"
    )
    assert bodies[2]["message"]["attachment"] == {
        "type": "image",
        "payload": {"url": "https://example.com/s.png"},
    }
    assert {"send_location", "send_contact", "send_sticker"} <= set(
        messenger.supported_operations
    )
    assert "send_location_request" not in messenger.supported_operations
