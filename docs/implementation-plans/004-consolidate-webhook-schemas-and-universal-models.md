# Implementation Plan: Consolidate Webhook Schemas and Universal Models

## Source Request

Requested from the source checkout:

`docs/tech-requests/004-consolidate-webhook-schemas-and-universal-models.md`

The clean worktree is based on commit `54373d5` and does not include that
untracked request file, so this plan uses the request text from the source
checkout and the committed architecture in this worktree.

## Grounding

Wappa's canonical runtime language says:

- `wappa/webhooks` owns platform webhook parsing into Universal Models.
- A Universal Model is the platform-agnostic representation that leaves
  Webhooks and enters dispatch.
- `PlatformType` remains the canonical enum for messaging platforms.
- `wappa/schemas` may keep shared primitives that are not inbound webhook
  schemas.
- Clean breaking changes are allowed; no compatibility shims for old inbound
  import paths.

The current committed tree has two competing inbound schema sources:

- `wappa/webhooks/**`: intended canonical inbound schemas and Universal Models.
- `wappa/schemas/**`: older duplicated inbound base models, WhatsApp models,
  webhook factory, and message schemas.

## Recommended Scope Decision

Keep `wappa/schemas` only for shared primitives and non-inbound request/response
models:

- Keep `wappa/schemas/core/types.py`.
- Keep `wappa/schemas/core/recipient.py`.
- Keep `wappa/schemas/__init__.py` only if it describes shared schemas
  accurately.
- Remove inbound schema modules from `wappa/schemas`:
  `core/base_message.py`, `core/base_status.py`, `core/base_webhook.py`,
  `factory.py`, and all of `wappa/schemas/whatsapp/**`.

Do not move `PlatformType` or `MessageType` in this request. They are shared
primitives used by inbound, outbound, domain factories, SSE, PubSub, expiry, and
tests. Moving them would broaden the change beyond the schema consolidation.

## Work Plan

1. Baseline the duplicate graph.
   - Run import inventory for `wappa.schemas.core.base_*`,
     `wappa.schemas.factory`, and `wappa.schemas.whatsapp`.
   - Confirm all remaining imports from `wappa.schemas` point only to
     `core.types` or `core.recipient`.
   - Capture current test status before edits if dependencies are available.

2. Update canonical imports.
   - Replace inbound base/model imports with `wappa.webhooks.core.*`.
   - Replace WhatsApp inbound imports with `wappa.webhooks.whatsapp.*`.
   - Replace schema factory imports with `wappa.webhooks.factory`.
   - Keep shared primitive imports from `wappa.schemas.core.types` and
     `wappa.schemas.core.recipient`.

3. Delete duplicate inbound schema modules.
   - Remove `wappa/schemas/factory.py`.
   - Remove `wappa/schemas/core/base_message.py`.
   - Remove `wappa/schemas/core/base_status.py`.
   - Remove `wappa/schemas/core/base_webhook.py`.
   - Remove `wappa/schemas/whatsapp/**`.
   - Update `wappa/schemas/core/__init__.py` and `wappa/schemas/__init__.py`
     to expose only shared primitives.

4. Tighten the canonical Webhooks package.
   - Ensure `wappa/webhooks/__init__.py` exports every public Universal Model
     and the WhatsApp platform schemas hosts are expected to import.
   - Keep `wappa/webhooks/core/types.py` as a temporary re-export only if
     existing internal imports depend on it during this cleanup. Do not add new
     behavior there.
   - If the adjacent clean-break request is implemented in the same delivery,
     rename `IncomingMessageWebhook` to `InboundMessageWebhook`; otherwise keep
     the current class name and document the pending rename.

5. Update docs.
   - Update `wappa/webhooks/ARCHITECTURE.md` so it states that Webhooks owns all
     inbound schema Pydantic models and Universal Models.
   - Update `wappa/webhooks/CONTEXT.md` only for glossary corrections; avoid
     implementation detail.
   - Update root `ARCHITECTURE.md` dependency rules so Webhooks no longer
     appears to depend on `wappa/schemas` for inbound models, only shared
     primitives.
   - Update `docs/public-contract.md` because public import paths change:
     old inbound imports under `wappa.schemas.*` are intentionally removed.

6. Add regression tests.
   - Add an import-boundary test proving `wappa.schemas` has no inbound webhook
     modules and that `wappa.schemas.whatsapp` cannot be imported.
   - Add WhatsApp parsing tests for message, status, error, system, and custom
     field payloads that validate platform payload schemas still become
     Pydantic Universal Models.
   - Add a small fake-platform processor test that maps a non-WhatsApp payload
     into the same Universal Model shape without adding a real platform adapter.
     Keep it local to tests so production support is not implied.

7. Verify public examples and templates.
   - Update CLI templates and examples importing Universal Models.
   - Search generated examples for old `wappa.schemas.whatsapp` or inbound
     base imports.
   - Leave outbound request/response examples using `RecipientRequest` and
     shared enum imports unchanged.

8. Run validation.
   - `uv run ruff check .`
   - `uv run mypy wappa`
   - `uv run pytest -q`
   - Repeat import inventory to prove no duplicate inbound source remains.

## Risk Areas

- `wappa.schemas.factory` and `wappa.webhooks.factory` are near duplicates.
  Delete the schemas copy only after all imports use the webhooks copy.
- Some message modules in `wappa/webhooks/whatsapp/message_types` may still
  import from `wappa.schemas.core.types`; that is acceptable for shared enums,
  but imports from `wappa.schemas.core.base_message` are not.
- The public contract changes intentionally break host imports from
  `wappa.schemas.whatsapp.*`. There should be no shim.
- Renaming `IncomingMessageWebhook` belongs to the adjacent clean-break request.
  Bundle it only if the release scope includes that request; otherwise this
  plan should not silently expand into a naming migration.

## Acceptance Mapping

- Webhooks owns inbound schemas: delete duplicate inbound modules from
  `wappa/schemas` and update imports.
- Universal Model forms remain Pydantic schemas: regression tests instantiate
  each form and assert `BaseModel` behavior.
- `wappa/schemas` contains only shared primitives/non-inbound models:
  import-boundary test plus file inventory.
- No dual source of truth: `wappa/schemas/whatsapp` and inbound base modules
  are gone.
- No compatibility import path: removed modules are not re-exported.
- WhatsApp parsing still passes: message/status/error/system/custom parsing
  tests.
- Future platform path documented: Webhooks architecture explains platform
  schema to Universal Model mapping, backed by the fake-platform test fixture.
