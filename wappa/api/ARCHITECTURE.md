# API Context — Architecture

Wappa's HTTP edge: the Meta webhook callback and the optional Messaging HTTP API. Route modules adapt HTTP to Wappa modules; Platform parsing, credential lookup, cache namespaces and dispatch policy live behind them. Decisions: [ADR-0007](../../docs/adr/0007-embedded-outbound-route-control.md), [ADR-0009](../../docs/adr/0009-route-capability-groups.md), [ADR-0016](../../docs/adr/0016-one-messenger-method-per-action.md), [ADR-0021](../../docs/adr/0021-platform-messaging-http-api.md). Contract: `docs/public-contract.md` ("Inbox Execution Context", "HTTP route composition").

## Router tree

`WappaCorePlugin` (`wappa/core/plugins/wappa_core_plugin.py`) mounts the health router (public) and `create_messaging_router(...)`; `Wappa` (`wappa/core/wappa_app.py`) mounts `create_webhook_router(...)` as public; `SSEEventsPlugin` mounts `/api/sse` from `wappa/api/routes/sse.py`.

```
/health, /health/detailed wappa/api/routes/health.py           health_router (public)
/webhook                  wappa/api/routes/webhooks.py          create_webhook_router
  /inboxes/{platform}       GET verify, POST callback -> api/controllers/webhook_controller.py
                            (400 unless {platform} is in wappa.platforms.PLATFORMS)
  /inboxes/instagram/deauthorize, /inboxes/{platform}/status, /platforms
/api/{platform}           wappa/api/routes/whatsapp_combined.py create_messaging_router
  reads (always)            whatsapp_health, media reads, messages/interactive/specialized info,
                            template info, conversation_reads_router (posts, comments, history)
  outbound_transport        messages, media, interactive, specialized send routers, private_reply_router
  template_transport        whatsapp_templates.py
  media_upload              POST /media/upload
  media_management          DELETE /media/{id}
  state_handler_api         whatsapp_state_handlers.py (/state-handlers/*)
  comment_controls          conversations.py comment_controls_router
/api/sse                  wappa/api/routes/sse.py               (SSEEventsPlugin)
```

The route modules live in `wappa/api/routes/whatsapp/` (the folder name is historical: the same routes serve every Platform) and `wappa/api/routes/conversations.py` (comments, post and history reads, private reply). A module that mixes capability groups mints one router per group from `RouteFamily` in `wappa/api/routes/whatsapp/route_families.py`, so the group is decided at the decorator. `wappa/api/routes/__init__.py` exports `create_messaging_router` and `health_router`.

## Inbox selection

`wappa/api/dependencies/inbox_context.py` owns it. The router-level `route_platform` dependency validates `{platform}` (`RoutePlatform`, derived from the installed Platforms in `wappa.platforms.PLATFORMS`: `whatsapp`, `instagram`). `select_inbox_ref` builds `InboxRef(path platform, X-Wappa-Inbox-ID)`; without the header it falls back to the legacy default Inbox only when that Inbox is on the path's Platform, else 400. `get_inbox_execution_context` resolves the active record once per request (unknown → 404, directory failures → 503) and returns the shared `InboxExecutionContext`. Send routes take `get_inbox_messenger`, which builds the Inbox's own Messenger through `OutboundRuntime`, so app Messenger middleware runs on API sends. Host authentication runs first; the header selects scope and grants nothing.

## Capability gates and status mapping (ADR-0021)

- `requires_capability(kind)` asks the Inbox's Messenger for a Focused Capability (`ICommentControls`, `IConversationContentReader`, `IConversationHistoryReader`, `IMediaLibrary` for media upload, download, info and delete, with no Platform branch) and answers 501 `"<platform> does not provide <kind>"` when it is missing.
- WhatsApp-only routes (Templates, Template info, media limits, validators, `/health`) reach the client through `InboxExecutionContext.whatsapp_client()` or `.template_transport()`, which call `whatsapp_only(...)` and answer the same 501. A capability method the Platform has no endpoint for (Instagram `IMediaLibrary.info`/`delete`) raises `UnsupportedOperationError`, which `map_send_errors` turns into the same 501.
- Send routes own no status mapping. Each builds its target with `direct_target(messenger, request)` and is decorated with `map_send_errors(operation)` (`wappa/api/utils/error_helpers.py`), the one mapper: `UnsupportedOperationError` → 501, `ValueError` (a local rule violation, raised before I/O) → 400, any other exception → 500, and a failed `MessageResult` (or `MediaUploadResult`) → the status its `error_code` maps to in `ERROR_CODE_MAPPING` (default 400) through `raise_for_failed_result`. Pydantic validation stays 422.

## Capability groups and profiles (ADR-0007, ADR-0009)

`WhatsAppRouteCapabilities` (in `wappa/api/routes/whatsapp/route_families.py`) has six groups: `outbound_transport`, `template_transport`, `media_management`, `media_upload`, `state_handler_api`, `comment_controls`. `WhatsAppRouteProfile.STANDALONE` mounts all but `template_transport`; `EMBEDDED` keeps only `media_upload` plus the reads. `resolve_capabilities` applies explicit overrides over the profile; passing `include_outbound_transport=False` without a profile implies `EMBEDDED`. Hosts set them through the `Wappa(route_profile=..., include_*_api=...)` constructor. Groups apply to every Platform at once.

## Event tracking

`dispatch_message_event` in `wappa/api/utils/event_decorators.py` decorates send routes: after the route returns a `MessageResult`, it builds an `APIMessageEvent` and submits `APIEventDispatcher` work (`process_api_message`) through `BackgroundWorkTracker`. The event's Platform is `result.platform`, the Platform that sent; the decorator takes none. The message-type label comes from `classify_outbound_payload` (`wappa/messaging/classification.py`) unless a route passes one. `map_send_errors` sits above it, so a failed result is still recorded (`response_success=False`) before the route answers its error status. The dispatcher comes from `get_api_event_dispatcher` in `wappa/api/dependencies/event_dependencies.py`.

## Request models

- Send request models subclass `DeliveryRequest` (`wappa/schemas/core/recipient.py`, carrying `recipient` plus every known address) and live in `wappa/messaging/whatsapp/models/`: `wappa/messaging/whatsapp/models/basic_models.py`, `wappa/messaging/whatsapp/models/media_models.py`, `wappa/messaging/whatsapp/models/interactive_models.py`, `wappa/messaging/whatsapp/models/specialized_models.py`, `wappa/messaging/whatsapp/models/template_info_models.py`.
- Route-local models: `CarouselMessage` in `wappa/api/routes/whatsapp/whatsapp_interactive.py`, `ContactRequest` / `LocationRequest` in `wappa/api/routes/whatsapp/whatsapp_specialized.py`, `CommentReplyRequest` / `PrivateReplyRequest` in `wappa/api/routes/conversations.py`.
- Template transport requests: `wappa/messaging/template_transport.py`. State handler requests: `wappa/api/models/handler_models.py`.

## Tests that pin the API

- `tests/test_platform_messaging_api.py`: `/api/{platform}` per Platform, Inbox selection, 501/400 mapping.
- `tests/test_router_tree_and_public_routes.py`: router-tree composition and public route prefixes.
- `tests/test_outbound_route_composition.py`: which URLs each profile and override mounts.
- `tests/test_api_event_tracking.py`: API events submit through `BackgroundWorkTracker`.
- `tests/test_inbox_execution_context.py`: header, legacy default and failure classes.

## Adding a route

1. Pick its capability group; mint its router from the module's `RouteFamily` and include it in the matching branch of `create_messaging_router`. A new group needs a `WhatsAppRouteCapabilities` field, both profiles, `resolve_capabilities`, the `create_messaging_router` and `Wappa` parameters, and an ADR-0009 review.
2. Depend on `get_inbox_messenger`, `requires_capability(kind)` or `get_inbox_execution_context`; never build a Messenger or client by hand.
3. Use a `DeliveryRequest` subclass for sends and build the target with `direct_target(messenger, request)`; the handler body is the one Messenger call.
4. Decorate send routes with `@map_send_errors("<operation>")` above `@dispatch_message_event()`, and teach `classify_outbound_payload` any new request model.
5. Cover it in `tests/test_platform_messaging_api.py` and, for a new group, `tests/test_outbound_route_composition.py`; update `docs/public-contract.md` and `CHANGELOG.md`.
