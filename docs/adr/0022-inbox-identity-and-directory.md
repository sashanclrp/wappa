# Inbox identity, the Inbox Directory and Delivery Addresses

Accepted, 2026-11-06. Consolidates the identity and directory decisions first recorded on 2026-05-16 (`inbox_id` replaces `tenant_id`), 2026-08-30 (encrypted Inbox Directory), 2026-11-03 (Instagram records) and 2026-11-05 (Delivery Addresses, qualified cache namespaces, startup reset). This ADR states the whole current decision; the earlier ADRs it absorbed were deleted.

## Context

Wappa once used `tenant_id` as its runtime identity although the value was always a WhatsApp `phone_number_id`. "Tenant" pulled business tenancy into a messaging runtime, and the Host Application (Symphonai's Owner → Channel → Inbox) owns that. Multi-Inbox routing then needed a credential authority that Wappa can read on every webhook and send without querying the Host database each time, without letting each Host invent its own cache rows, indexes and token handling. A second Platform showed that a raw ID is unique only inside one Platform, and a WhatsApp reply to a BSUID failed while the same webhook carried a deliverable phone.

## Decision

### Identity

1. **The Inbox is Wappa's runtime scope.** An Inbox is the Platform-facing message ingress and egress identity. Its globally unique identity is `InboxRef(platform, inbox_id)`; the raw `inbox_id` is unique only inside one Platform (WhatsApp `phone_number_id`, Instagram professional-account ID). `PlatformAccountRef(platform, platform_account_id)` names the Platform-side grouping (a WhatsApp WABA; on Instagram the professional account is both Platform Account and Inbox, with matching native IDs, never a fabricated WABA). Business tenancy, Owner and Channel are Host concepts with no Wappa term.
2. **One cache namespace rule.** Every Inbox-scoped key starts with `InboxRef.cache_namespace`, `<platform>__<inbox_id>`, WhatsApp included. `InboxRef.from_cache_namespace` rejects an unqualified namespace. Pre-0.34 WhatsApp keys move once with the explicit `wappa migrate cache-namespaces -i <phone_number_id> ...` (dry run unless `--apply`; Redis `RENAMENX` keeps TTLs and never overwrites); nothing is inferred from key shapes.

### Credential authority

Deployment variables use Wappa-owned `SYSTEM_`, `META_` and `REDIS_` clusters; only hosting contracts `PORT`, `DATABASE_URL`, `REDIS_URL` are unprefixed. Since 0.34.3 retired names fail at settings initialization with their replacements, even if empty; no aliases. Provider configuration is Host-owned.

3. **One authority per process.** `InboxRoutingMode` is `legacy` (the `META_WHATSAPP_*` settings bundle, one WhatsApp Inbox) or `explicit` (the Inbox Directory). They are mutually exclusive: no `auto` mode, no fallback from one to the other.
4. **Wappa owns the Inbox Directory.** `InboxDirectoryTable` and `InboxDirectory` are concrete Wappa modules over `ITableCache` under the reserved System Scope `__system__`; Hosts cannot replace the model, cache shape, TTLs, indexes or mutation behaviour. Hosts adapt their durable schema through one read-only port, `IInboxDirectorySource` (`get_inbox(inbox_ref)`, `list_inboxes_for_platform_account(account_ref)`). The internal `IInboxCredentialResolver` is not a Host extension point.
5. **Only Wappa mutates the directory.** Hosts commit durable state, then call the idempotent `refresh_inbox(inbox_ref)` or `deactivate_inbox`. Wappa writes the primary row before derived indexes, repairs partial work on retry and evicts cached Messengers. There is no `upsert_inbox(record)`.
6. **Freshness.** Active rows and active account indexes have a 60-minute sliding TTL; inactive, absent and empty-account rows a fixed 60-minute TTL. A miss makes one source call; source or cache failures never become negative records. In explicit mode a startup hook (priority 25) deletes only the two directory tables, so changes made while Wappa was down apply on first use without a startup stampede. Changes made while Wappa runs still need `refresh_inbox`.
7. **Versions.** `credential_version` is a positive integer, monotonic over the lifetime of one `InboxRef`; higher wins, equal is accepted only for an identical canonical record. `updated_at` is evidence, never ordering.
8. **Encrypted canonical records.** Credentials are encrypted with `SYSTEM_TOKEN_ENC_KEY` (Fernet, `SYSTEM_TOKEN_ENC_PREVIOUS_KEYS` accepted on read) into a context-bound `EncryptedSecretEnvelope` bound to format version, Platform, `inbox_id` and field name. Hosts persist envelopes and never decrypt them. Tokens are never hashed: Meta needs the exact bearer value. The record union is static, and `RECORD_TYPES` maps each Platform to its active and inactive record classes so no service branches on Platform.
9. **The account index is a projection.** Every listed member is checked against its primary record; a stale member triggers one synchronous source reload and repair; failure is `503`, never a dispatched subset.

### Addressing

10. **One way to address: an explicit target on every send.** `DirectMessage(inbox_ref, addresses=DeliveryAddresses)` names the recipient; the Messenger knows only its Platform, Inbox and credentials. `DeliveryAddresses.of(*addresses)` states every known address of one User, never a strategy; `webhook.user.delivery_addresses()` builds it (WhatsApp BSUID and phone, Instagram scoped ID). The Parent BSUID is identity evidence, not a fallback.
11. **The Platform adapter normalizes, excludes, orders and falls back.** WhatsApp removes phones proven to echo a numeric regular/Parent BSUID suffix, retains raw evidence and then sends to the phone first, then the BSUID (Meta: `to` takes precedence), and falls back only after a synchronous rejection of the address itself (`131030`, `131062`); window, rate, content, undeliverable, timeout and 5xx errors return as-is. Authentication Templates go to phones only. `MessageResult.attempted_recipients` lists every address tried. Instagram has one address per User.

Generic reference constructors are canonical, with matching WhatsApp and Instagram factories. UserIdentity qualifies the existing recommended User ID, Delivery Addresses and optional evidence by Inbox. DeliveryAddresses.evidence carries corroboration without making Parent evidence a fallback. Durable identity reconciliation remains Host-owned.

## Consequences

- Hosts write no cache rows and no cipher: one source adapter, `InboxCredentialService.create_active_record` / `rotate_active_record` before persistence, `refresh_inbox` after commit.
- A directory outage is `InboxDirectoryUnavailableError` (503); an unknown or inactive Inbox `InboxNotFoundError`; a wrong-account relation `InboxMembershipError`; an unusable envelope `InboxCredentialIntegrityError`. Nothing collapses to "unknown Inbox".
- TTL is never revocation: a deactivated Inbox stays usable until the Host calls `deactivate_inbox`. Removing an old encryption key is safe only after durable re-encryption and the 60-minute TTL window.
- Deploying 0.34 over 0.33: stop workers, run the namespace migration, start 0.34; Pub/Sub channels become `wappa:notify:whatsapp__<pnid>:...`.
- The JSON backend keeps one file-level expiry per scope and stays a single-process development backend.
- Unconfirmed in Meta's docs and recorded as live evidence only: the `131030` code and whether test-number allow-lists accept BSUIDs.

## Alternatives rejected

- Keeping `tenant_id`, renaming to `channel_id` (a Host term) or `phone_number_id` (Platform-specific), or an alias period: names shape thinking, and dual names create ambiguity.
- An open `IInboxCredentialStore`, Host-written directory rows or an `upsert`, a directory-specific Redis adapter: Hosts could change active-Inbox rules and Wappa could not guarantee validation, indexes or ordering.
- `SecretStr` alone or hashed tokens at rest; Redis as runtime authority with Hosts publishing records.
- Binding the recipient into the Messenger (two ways to address, against one-method-per-action), a one-address target (every Host re-codes the fallback), and reloading every Inbox at startup.
- Keeping the raw WhatsApp namespace exception (two rules forever).
