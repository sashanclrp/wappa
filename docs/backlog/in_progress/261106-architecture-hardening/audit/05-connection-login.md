# Inbox connection and Login (core interface 5)

Status reviewed 2026-11-06: historical pre-hardening audit. Findings and file:line references below describe the audited baseline. Use the [plan status table](../plan.md#code-reality-2026-11-06) for implemented and remaining work; do not rebuild a resolved finding from this snapshot.


## Summary

Core interface 5 already exists and is a real seam. `IInboxConnector` (`wappa/connections/contract.py:175-221`) has two adapters, `WhatsAppConnector` and `InstagramConnector`, built on one Meta-scoped core, `MetaBusinessLogin`. The connections package has no Platform if/elif. Verification confirmed six of the auditor's seven findings, some narrowed or with corrected severity, and rejected one (05-7, a registry the auditor itself said not to build). It added one finding: `activate` never checks that the grant belongs to its connector's Platform. The sharpest issue is the Instagram deauthorize side door. In it, a route builds its own Dispatch Context, and the connections package imports the webhooks layer. The rest are low-severity cleanups: record-class selection repeated in `InboxCredentialService`, a second Graph transport inside `InstagramSubscriptions`, a WhatsApp-named constant and health probe in Platform-neutral code, `Any`-typed records at the seam, and a stale backlog draft. No live code uses the stale names (`InboxCredentialsService`, `IInboxCredentialStore`, `owner_id`).

## Confirmed findings

### 05-1 Instagram deauthorize is a Platform-specific side door that bypasses the inbound runtime and inverts layering

- Files: `wappa/api/routes/webhooks.py:103-140`, `wappa/connections/instagram.py:368-410`, `wappa/connections/__init__.py:24-33`, `ARCHITECTURE.md:246-284`, `docs/public-contract.md:316`
- Principle: platform-leak
- Severity: medium
- Breaking: yes if `deauthorization_event` moves out of `wappa.connections`. Public surfaces: `wappa.connections.deauthorization_event`, `POST /webhook/inboxes/instagram/deauthorize` (the route can keep its path).
- Evidence: The route builds a Dispatch Context itself. It calls `DispatchContextBuilder.from_app` and `builder.bind_handler(..., user_id="__system__", messenger=None, ...)`, hard-codes `InboxRef(platform=PlatformType.INSTAGRAM, ...)` and calls `dispatch_universal_webhook` (`webhooks.py:125-139`). This repeats the binding that `wappa/core/inbound/runtime.py:331-365` (`_create_dispatch_handler`) owns. It also breaks the edge-ownership rule at `ARCHITECTURE.md:284`, which says route modules only adapt HTTP and that dispatch policy lives behind them. Unlike the runtime path, the route never consults the Inbox Directory: any signed `user_id` is dispatched, whether or not it is a known Inbox. `deauthorization_event` lives in the connections package but imports `wappa.webhooks.core.webhook_interfaces` inside the function (`instagram.py:381-387`) to build an inbound webhook object. That is webhook parsing, which belongs in the Instagram webhook adapter. The Layer Dependencies diagram (`ARCHITECTURE.md:248-280`) has no Connections layer at all. The callback also cannot fire for grants Wappa's own `InstagramConnector` creates. `docs/public-contract.md:316` says Unified Login issues `SYSTEM_USER` tokens that receive no deauthorize, and the live runs at `docs/backlog/in_progress/261103-instagram-conversations/tests/live-test-plan.md:216-226` saw no callback.
- Deletion test: Delete the route's inline dispatch block and the binding logic has to reappear somewhere. The right place is the inbound runtime, which already does it once, so moving it there concentrates the logic. Delete `deauthorization_event` and signed_request-to-`InboxConnectionWebhook` translation moves to every Host that uses Instagram Login. Keep the function, but in the webhooks layer.
- Proposed fix: Move `deauthorization_event` to `wappa/webhooks/instagram/` as the parser of that non-JSON delivery. `parse_signed_request` stays in `meta_login`. Add one runtime entry for dispatching a Platform-originated system event: the inbound runtime's existing handler binding, with no Messenger and a directory lookup for the Inbox. The route then only adapts HTTP: read form, parse, call runtime. Do not invent a Platform-neutral "non-JSON delivery" adapter method, because only Instagram has this callback (that would be a hypothetical seam). Document in the module that it serves Instagram Login grants only. List the moved import in CHANGELOG under the clean-cut rule.
- ADR conflict: none. ADR-0025 line 43 names the route as the Instagram source of `InboxConnectionWebhook`, and that stays true.

### 05-2 InboxCredentialService selects Platform record classes with ternaries and a literal Platform set

- Files: `wappa/domain/inbox/services.py:76-96`, `wappa/domain/inbox/services.py:112-126`, `wappa/domain/inbox/services.py:128-141`, `wappa/domain/inbox/services.py:143-148`, `wappa/domain/inbox/credentials.py:134-221`
- Principle: OCP
- Severity: low (auditor said medium; there are two Platforms, `_require_platform` guards the else-branch, and `ARCHITECTURE.md:308` documents "record selection in services.py" as a known per-Platform touch point)
- Breaking: no. Public surfaces: none (internal selection only).
- Evidence: `create_active_record` picks `InstagramActiveInboxCredentialRecord if inbox_ref.platform is PlatformType.INSTAGRAM else WhatsAppActiveInboxCredentialRecord`. `create_inactive_record` repeats the pattern for inactive records. `rotate_encrypted_record` isinstance-checks both active classes by name, although every record has `is_active` (`credentials.py:142,153,171,188`). `_require_platform` holds the literal set `{WHATSAPP, INSTAGRAM}`. Each record class already declares its `platform` and `status` as Literals, so the union (`credentials.py:192-221`) knows the mapping, and the service restates it in four places.
- Deletion test: Replace the four sites with one lookup and the complexity disappears rather than moving elsewhere. The discriminated union itself is the right home for per-Platform record shape and stays.
- Proposed fix: Next to the union in `credentials.py`, add one table, `RECORD_TYPES: dict[PlatformType, tuple[type[Active], type[Inactive]]]`. The service and `_require_platform` read it, and an unknown Platform becomes a `ValueError`. Use `record.is_active` in `rotate_encrypted_record`. Keep the four classes, since the Instagram `inbox_id == platform_account_id` validator is a real difference.
- ADR conflict: none.

### 05-3 Platform-neutral credential code names WhatsApp in its secret-binding constant and health probe

- Files: `wappa/domain/inbox/services.py:58-67`, `wappa/domain/inbox/services.py:191-198`, `wappa/domain/inbox/services.py:443-447`
- Principle: platform-leak
- Severity: low
- Breaking: no in practice. `WHATSAPP_ACCESS_TOKEN_FIELD` appears only in the module `__all__`, and neither `docs/public-contract.md` nor the tests reference it. Drop it from `__all__` under the clean-cut rule and note it in CHANGELOG. Public surfaces: `wappa.domain.inbox.services.WHATSAPP_ACCESS_TOKEN_FIELD`.
- Evidence: `_binding()` sets `credential_field_name=WHATSAPP_ACCESS_TOKEN_FIELD` for every Platform's envelope, Instagram included. `InboxDirectory.check_health` probes with `InboxRef.whatsapp("0")` (line 195), which makes a Platform-neutral directory check name one Platform. The constant's value, `"access_token"`, is Platform-neutral. Only the name leaks.
- Deletion test: n/a. Renaming removes a false coupling at no cost. The value must stay `"access_token"` so existing envelope AAD still decrypts.
- Proposed fix: Rename the constant to a private `_ACCESS_TOKEN_FIELD` with the value unchanged. Have the health probe read a fixed sentinel row (for example `InboxRef(platform=next(iter(PlatformType)), inbox_id="0")`), or give the table a `ping()`. The auditor called `settings_resolver.py` WhatsApp-only and legitimate, and that holds (see below).
- ADR conflict: none.

### 05-4 InstagramSubscriptions carries a second Meta Graph transport; connector `complete` duplicates the authorization prelude

- Files: `wappa/connections/instagram.py:112-220`, `wappa/connections/meta_login.py:196-257`, `wappa/connections/whatsapp.py:100-155`, `wappa/connections/instagram.py:266-310`
- Principle: DRY
- Severity: low
- Breaking: yes for the `InstagramSubscriptions` constructor if it takes the shared transport. Public surfaces: `wappa.connections.InstagramSubscriptions` (exported, `docs/public-contract.md:79`).
- Evidence: `InstagramSubscriptions` builds its own Graph base URL, Bearer header, 20-second timeout and transport-error handling (`instagram.py:112-220`). `_subscribe_call` (`instagram.py:127-147`) repeats the logic of `MetaBusinessLogin.success_call` (`meta_login.py:236-257`) line for line, including the `(True|None|False, code)` tri-state and `INDETERMINATE`. `unsubscribe` (`instagram.py:208-220`) is a weaker copy that collapses "unknown" into `False`. WhatsApp uses `success_call` for the same `subscribed_apps` calls (`whatsapp.py:179-181, 202-204`). In `complete`, the sequence consume → `exchange_code` → `token_debug` → `scopes_of` → `ConnectionGrant(inboxes=())` → `model_copy(inboxes=...)` appears in both adapters, and only discovery differs. The auditor's `begin` and constructor duplication is real but small: a three-line delegate and the construction of the shared core.
- Deletion test: Remove `InstagramSubscriptions`' private transport and nothing moves elsewhere, because `MetaBusinessLogin` already provides it, so the complexity disappears. The `complete` prelude appears in two callers and would appear in a third Meta connector.
- Proposed fix: Give `InstagramSubscriptions` the `MetaBusinessLogin`, or a small Graph transport extracted from it, and route `subscribe`, `unsubscribe` and `subscribed_fields` through `success_call` and `get`. Add one method on `MetaBusinessLogin`, for example `authorize(state, host_subject, code, error, error_reason) -> (intent, token, expires_at, scopes, targets)`, which both `complete` methods call before their own discovery. Do not introduce a template-method base class: the remaining per-adapter variation (discovery, readiness, subscription, identity mapping) is most of the code, and an abstract base would add a second layer of indirection on top of the seam that already exists.
- ADR conflict: none. ADR-0026 decision 2 (shared Meta core plus per-Platform strategy) already describes this split.

### 05-5 The connector seam erases the CredentialRecord type with Any

- Files: `wappa/connections/contract.py:158-170`, `wappa/connections/contract.py:200-208`, `wappa/connections/contract.py:223-243`, `wappa/connections/whatsapp.py:168-175`, `wappa/connections/instagram.py:331-338`
- Principle: missing-interface
- Severity: low
- Breaking: no at runtime (annotation-only). Public surfaces: `ActivationResult.record`, `IInboxConnector.activate(previous=...)`, `wappa.connections.contract.build_record`.
- Evidence: `ActivationResult` has `record: Any` with `arbitrary_types_allowed=True` (lines 161-163). `activate(..., previous: Any | None = None)` (line 207) is repeated in both adapters, and `build_record(..., previous: Any | None) -> Any` (lines 228-229) reads `previous.inbox_ref`/`is_active` untyped. `contract.py:30-31` already imports from `wappa.domain.inbox`, so there is no cycle preventing `CredentialRecord` / `ActiveInboxCredentialRecord` (`credentials.py:192-198`). `ActivationResult.record` is the single object a Host persists, so this is where the type matters most. The auditor's line numbers (144, 192) were off. These are the lines in the file as it stands.
- Deletion test: n/a. This is a typing gap at the seam, not a module question.
- Proposed fix: Type `record: ActiveInboxCredentialRecord`, `previous: CredentialRecord | None`, and `build_record -> ActiveInboxCredentialRecord`. Drop `arbitrary_types_allowed` if nothing else needs it.
- ADR conflict: none.

### 05-6 The connector backlog draft is stale against ADR-0026 and the shipped code

- Files: `docs/backlog/in_progress/261105-mid-inbox-connector-contract.md:10-41`, `docs/adr/0026-inbox-connection.md:22-30`, `wappa/connections/whatsapp.py:10-19`
- Principle: stale-doc
- Severity: low
- Breaking: no. Public surfaces: none.
- Evidence: "Today" says Instagram is `InstagramUnifiedLogin` and WhatsApp Embedded Signup lives in Symphonai. ADR-0026 Consequences records that `InstagramUnifiedLogin` was replaced, and `WhatsAppConnector` exists. "Proposed shape" sketches `begin(intent)`, `activate(inbox)` and `disconnect(inbox)`. The shipped contract is `begin(host_subject)`, `activate(grant, inbox_ref, credentials, previous)` and `disconnect(inbox_ref, account_ref, token)`. The table says WhatsApp activate does "register the number", but ADR-0026 Consequences and `whatsapp.py:18-19` say `/register` is deliberately not called. "Remaining" includes a Symphonai migration step, which is Host work outside Wappa.
- Deletion test: n/a.
- Proposed fix: Keep only the open Wappa items: the live Gate B and Embedded Signup run, the credential-step result for non-OAuth Platforms, and optional `/register`. Point to ADR-0026 for the shape. Move the Symphonai step to the Symphonai backlog.
- ADR conflict: none.

### 05-8 `activate` does not check that the grant belongs to its connector's Platform (added by verifier)

- Files: `wappa/connections/contract.py:129-145`, `wappa/connections/whatsapp.py:168-190`, `wappa/connections/instagram.py:331-358`
- Principle: LSP
- Severity: low
- Breaking: no. Public surfaces: `IInboxConnector.activate`.
- Evidence: `ConnectionGrant` carries `platform` (line 133), but neither adapter's `activate` compares `grant.platform` or `inbox_ref.platform` with `self.platform`. `grant.inbox(inbox_ref)` matches only by `InboxRef` equality (lines 141-145). A multi-Platform Host that looks up a connector by Platform and passes the wrong grant gets a Graph call on the wrong ID instead of a clear error. For example, `InstagramConnector.activate` given a WhatsApp grant and a phone-number `InboxRef` subscribes `/{phone_number_id}/subscribed_apps` with Instagram fields. `rg` over `wappa/connections` finds no such guard.
- Deletion test: n/a. This is a missing precondition on the shared contract, and it belongs once in shared code, not in each adapter.
- Proposed fix: Have `build_record` or a small shared helper raise `ValueError` when `grant.platform` or `inbox_ref.platform` differs from the connector's Platform, and have both adapters call it first. That is one check, with no new type.
- ADR conflict: none.

## Rejected findings

- 05-7 "No Platform-keyed connector lookup, so Hosts branch on Platform to pick a connector". Rejected. Nothing inside Wappa consumes connectors, and the auditor's own fix is "do not add a registry". ADR-0025 and ADR-0026 decision 3 (`docs/adr/0026-inbox-connection.md:15`) put routes and connect orchestration with the Host. A `dict[PlatformType, IInboxConnector]` written in the Host is ordinary composition, not a Platform branch in shared code. Labelling the absence a hypothetical seam inverts the principle: adding the registry would create the hypothetical seam. At most, add one line to the unified-login skill reference. That does not make it an architecture finding.
- Auditor sub-claim in 05-2 that the else-branch "silently maps any non-Instagram Platform to WhatsApp". Rejected as stated. `create_active_record` calls `_require_platform` first (`services.py:84`), and `create_inactive_record` only receives an existing `CredentialRecord`, which is already one of the four union members. The lookup table is still worth having for OCP reasons.
- Auditor sub-claim in 05-4 that `begin` and the constructor duplication justify a `MetaInboxConnector` template base class. Rejected as over-engineering. The duplicated `begin` is a three-line delegate, and an abstract base on top of `IInboxConnector` adds a second seam with the same two adapters. The narrowed fix (shared transport plus one `authorize` prelude) removes the real duplication.

## Checked and legitimate

- `wappa/connections/contract.py:175-221` `IInboxConnector`: one neutral InboxConnection seam with two real adapters, kept apart from `IMessenger` as ADR-0026 decides. It passes the two-adapter test.
- `wappa/connections/contract.py` `IConnectionIntentStore` plus `InMemoryConnectionIntentStore`: a Host-adaptation seam. Hosts supply the durable store (ADR-0025, ADR-0026), and the in-memory adapter serves tests and examples.
- `wappa/connections/meta_login.py` `MetaBusinessLogin`: shared by exactly the two Meta adapters. Its name and location make the Meta scope explicit, and it does not claim to be Platform-neutral.
- `wappa/domain/inbox/credentials.py:134-221`: the discriminated Platform x status record union is the right home for the per-Platform record shape. ADR-0022 and `ARCHITECTURE.md:299` ("grows one member per Platform") cover it.
- `InboxRef.whatsapp` / `PlatformAccountRef.whatsapp` factories in `wappa/domain/inbox/identity.py`: convenience constructors over the neutral `InboxRef(platform, inbox_id)`. They are used inside the WhatsApp adapter (`whatsapp.py:145-146`). Their one misuse in neutral code is 05-3.
- `wappa/domain/inbox/settings_resolver.py`: the documented legacy `WP_*` single WhatsApp Inbox resolver. Being WhatsApp-only is its stated purpose.
- The asymmetry in `disconnect` (WABA-wide in `whatsapp.py:193-205`, per account in `instagram.py:361-365`) is a Platform property documented in the contract docstring (`contract.py:212-221`) and in ADR-0026 Consequences. It is not a branch in shared code.
- The Instagram `account_id == inbox_id` identity mapping in `instagram.py:297-302` and the credential validators: Platform-specific identity mapping kept inside the adapter and record, as `ARCHITECTURE.md:284` requires.
- Stale names: `InboxCredentialsService`, `IInboxCredentialStore` and `owner_id` appear only in history (CHANGELOG, ADR-0022 annotated as replaced, superseded tech requests), in absence-asserting tests and in the CONTEXT.md Anti-Language table. No live code uses them.

## Interface proposal

Keep `IInboxConnector` as InboxConnection (CONTEXT.md term: Inbox Connector). Its four actions are already one method per action, as ADR-0025 requires. Change only the types and one precondition:

```python
class IInboxConnector(ABC):
    @property
    def platform(self) -> PlatformType: ...
    async def begin(self, host_subject: str, *, metadata: dict[str, str] | None = None) -> AuthorizationRequest: ...
    async def complete(self, *, state: str | None, host_subject: str, code: str | None = None,
                       error: str | None = None, error_reason: str | None = None) -> ConnectionGrant: ...
    async def activate(self, grant: ConnectionGrant, inbox_ref: InboxRef, *,
                       credentials: InboxCredentialService,
                       previous: CredentialRecord | None = None) -> ActivationResult: ...
    async def disconnect(self, inbox_ref: InboxRef, account_ref: PlatformAccountRef, token: SecretStr) -> bool: ...
```

- `ActivationResult.record: ActiveInboxCredentialRecord`. `activate` raises `ValueError` when `grant.platform` or `inbox_ref.platform` is not `self.platform`.
- Adapters: `WhatsAppConnector` and `InstagramConnector` on `MetaBusinessLogin`. Both call a shared `MetaBusinessLogin.authorize(...)` prelude, and `InstagramSubscriptions` uses the core's transport. No template base class.
- Not built until a second non-Meta adapter exists: the credential-step `begin` result (ADR-0026 Consequences) and a Wappa-owned connector registry.
- Inbound connection-state changes are not part of this interface. `InboxConnectionWebhook` arrives through PlatformWebhooks (WhatsApp `account_offboarded`, the Instagram deauthorize parser in `wappa/webhooks/instagram/`) and dispatches through the inbound runtime (05-1).
