# Many Inboxes on one Wappa app

## Contents

- Routing modes
- The Directory Source
- Records and credentials
- Adding, rotating and removing an Inbox
- Callbacks and HTTP selection
- Sending outside a dispatch
- Credential access for other services
- Identity resolution

## Routing modes

In this file `app` is the FastAPI app (`app.state...`, `from_app(app)`): `request.app` inside a route, or `wappa.asgi` for your `Wappa` object.

| | `legacy` (default) | `explicit` |
| --- | --- | --- |
| Inboxes | one WhatsApp number from env | any number of WhatsApp and Instagram Inboxes |
| Credentials | `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, `WP_BID` | the Host's `IInboxDirectorySource`, encrypted with `SYSTEM_TOKEN_ENC_KEY` |
| Instagram | no | yes |

Choose one with `Wappa(inbox_routing=InboxRoutingMode.EXPLICIT, inbox_directory_source=MySource())` or `SYSTEM_INBOX_ROUTING_MODE=explicit`. There is no fallback between modes: explicit mode refuses the `WP_*` variables at startup, and legacy mode refuses a source. `wappa init --inbox-routing explicit` scaffolds the explicit shape, including an `inbox_directory_source.py` module in the app package. Generate a key with `CredentialCodec.generate_key()` (`from wappa.core.security import CredentialCodec`) and rotate keys with `SYSTEM_TOKEN_ENC_PREVIOUS_KEYS` (comma-separated).

## The Directory Source

The only Host port, a two-method `Protocol`:

```python
from wappa import IInboxDirectorySource, InboxRef, PlatformAccountRef
from wappa.domain.inbox import InboxCredentialRecord

class MySource(IInboxDirectorySource):
    async def get_inbox(self, inbox_ref: InboxRef) -> InboxCredentialRecord | None:
        ...  # read your table; return the stored Wappa record, or None
    async def list_inboxes_for_platform_account(self, account_ref: PlatformAccountRef) -> tuple[InboxCredentialRecord, ...]:
        ...  # every record of one WABA or Instagram account
```

Store each record with `dump_record_for_storage(record)` (the only dump that keeps the ciphertext) and rebuild it with `parse_inbox_credential_record(stored)`, both from `wappa.domain.inbox`. Wappa caches what the source returns, encrypts and decrypts it, and evicts Messengers when a record changes. The source never decrypts anything. Webhooks for an Inbox the source doesn't know answer 400; Wappa never auto-registers accounts.

## Records and credentials

`from wappa.domain.inbox import WhatsAppActiveInboxCredentialRecord, InstagramActiveInboxCredentialRecord` (each has an inactive twin). Build them only through the runtime's `InboxCredentialService` (`app.state.inbox_runtime.credential_service`, explicit mode only):

```python
svc = app.state.inbox_runtime.credential_service
record = svc.create_active_record(inbox_ref=ref, account_ref=acct, access_token=SecretStr(token))
rotated = svc.rotate_active_record(previous, access_token=SecretStr(new_token))   # version + 1
revoked = svc.create_inactive_record(previous)                                     # version + 1
```

`InboxRef.whatsapp(phone_number_id)` and `PlatformAccountRef.whatsapp(waba_id)` build WhatsApp identities. Build Instagram ones with `InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=ig_id)` (`from wappa.schemas.core.types import PlatformType`). For Instagram, `platform_account_id` equals `inbox_id`. Connectors (the `wappa-apps` skill, its connecting-accounts reference) build records for you through `activate(...)`.

## Adding, rotating and removing an Inbox

1. Build or rotate the record (above, or `connector.activate`).
2. Commit it in the Host's transaction.
3. `await app.state.inbox_runtime.directory.refresh_inbox(inbox_ref)`: Wappa reloads it and evicts the cached Messenger.

To remove one, commit the inactive record, then `await directory.deactivate_inbox(inbox_ref)` (it raises `InboxMutationConflictError` if your source still says active). Calls already in flight finish with the old credential. In explicit mode, the directory cache is cleared at startup, so a restart always reads the source.

A reconnect still reaches you after that. A signed WhatsApp `account_reconnected` for a known inactive Inbox arrives on `process_inbox_connection` with `self.messenger` set to `None`; see `wappa-apps`' `connecting-accounts.md`. Your source's `list_inboxes_for_platform_account` must include inactive records for account-only events to find them. Ordinary messages to an inactive Inbox stay refused.

## Callbacks and HTTP selection

- Meta callbacks: `GET`/`POST /webhook/inboxes/whatsapp` and `/webhook/inboxes/instagram`, one Meta app. `META_APP_SECRET` checks every POST body before parsing (bad signature 401), `WP_WEBHOOK_VERIFY_TOKEN` answers only the GET challenge, an unknown or inactive Inbox answers 400, and a directory outage answers 503 (Meta retries).
- Wappa's HTTP API (`/api/{platform}/...`) selects the Inbox from the `X-Wappa-Inbox-ID` header (the phone number ID or Instagram account ID): missing with no default 400, unknown 404. Selecting grants nothing: authenticate and authorize first.
- In your own routes, depend on `get_inbox_execution_context` (`from wappa.api.dependencies import get_inbox_execution_context`; the route path must declare `{platform}`) instead of reading the header yourself.

## Sending outside a dispatch

```python
from wappa.messaging import DeliveryAddresses, DirectMessage, OutboundRuntime

runtime = OutboundRuntime.from_app(app)
messenger = await runtime.messenger(inbox_ref)                 # middleware included
await messenger.send_text("Your order shipped", target=DirectMessage(
    inbox_ref=inbox_ref, addresses=DeliveryAddresses.of(*stored_addresses)))
templates = runtime.templates(inbox_ref)                      # WhatsApp Templates; REJECTED elsewhere
```

Use it for jobs, agent replies and human takeover. Store every Delivery Address you saw for a User (phone and BSUID on WhatsApp), not one: save `list(webhook.user.delivery_addresses().values)` with the `InboxRef` in your User record, and rebuild the target with `DeliveryAddresses.of(*stored)`. Save the inbound message time too if you guard the 24-hour window. Apply your takeover and pause checks right before each send, including sends scheduled earlier. `runtime.platform_messenger(inbox_ref)` returns the Platform Messenger when you need Platform-only actions.

## Credential access for other services

```python
from wappa.domain.inbox import InboxCredentialAccess
credential = await InboxCredentialAccess.from_app(app).resolve(inbox_ref)
headers = credential.authorization_header()
```

Use it only for trusted adapters Wappa doesn't cover (publishing, insights). Authorize the caller first. Resolve per operation, never cache, and keep it out of logs, AI tool arguments and browsers.

## Identity resolution

`app.set_identity_resolver(resolver)` plugs an `IIdentityResolver` (`async resolve(recipient, *, inbox_ref) -> str`) that maps a Delivery Address to your canonical User within one Inbox, for example when one person's phone and BSUID must share state. The default `PassthroughIdentityResolver` keys by the address Meta sent. Key the lookup on the whole `inbox_ref`, and read the Platform from `inbox_ref.platform`: a numeric `recipient` proves nothing, and two Platforms can share a raw ID. Matching customers across Platforms is your business logic, not the resolver's.

The resolver runs on scheduled dispatch, `self.scope`, API events, API handler state and Template state. Webhook intake doesn't call it: handlers are keyed by `webhook.user.user_id`, so if you want a canonical User there, map it in your handler.
