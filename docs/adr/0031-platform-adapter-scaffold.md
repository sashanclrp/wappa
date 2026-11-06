# One scaffold for every Platform adapter, and no god files

Accepted, 2026-11-06 (user decision after the Instagram adapter drifted from WhatsApp's layout). Extends [ADR-0028](0028-whatsapp-first.md) and [ADR-0025](0025-messenger-contract.md) to code structure.

## Context

Instagram was scaffolded flat while WhatsApp had `client/`, `handlers/`, `services/` and `utils/` folders, and both Platforms' translators sat in a separate `wappa/processors/` package. The same responsibility lived in differently named places, the composition root knew WhatsApp's internals and not Instagram's, and several modules passed 1000 lines. Nothing failed when this happened, so it kept drifting.

## Decision

1. **One adapter shape per direction.** Every Platform has `wappa/messaging/<platform>/` and `wappa/webhooks/<platform>/` in the tree written down in `.agents/skills/wappa-develop/references/scaffolding.md`. A Platform omits a family it lacks; it never adds an empty module for symmetry.
2. **The translator lives with its Platform.** `wappa/processors/` is removed: a Platform's wire models, message types, routing and processor change together for the same reason. The processor stays the anti-corruption layer, and pure models never import it. `ProcessorError` is neutral and moves to `wappa/core/inbound/errors.py`.
3. **One composition module per Platform.** `wappa/platforms/` replaces `wappa/platforms.py`. Only `wappa/platforms/<platform>.py` knows how a Platform's adapters are constructed, and a new Platform adds that file and one line in `_INSTALLED`.
4. **Outbound code is not a "handler".** The word belongs to the Host's `WappaEventHandler`. WhatsApp's per-family handlers fold into `messenger/` mixins and `payloads/` builders, and `WhatsAppMediaHandler` becomes `WhatsAppMediaTransport`. `utils`, `helpers` and `services` folders are not allowed.
5. **No module passes 450 lines, with no exception list.** A module past the ceiling becomes a package named after its stem, with the `refactor-backend-god-files` skill.
6. **A test enforces it.** `tests/test_platform_scaffold.py` fails on a scaffold violation or an oversized module. Changing the scaffold changes that test, the reference and the context `ARCHITECTURE.md` trees in one change.

## Consequences

- A maintainer who knows one adapter knows all of them, and a third Platform copies the tree.
- Internal import paths moved. Documented ones are listed as breaks in `CHANGELOG.md`, with no shims. A package named after an old module keeps that import path.
- Splitting big classes into mixins keeps their public API and adds indirection when reading one class; `adapter.py` and `_base.py` are the entry points.
- Not decided here: adapter constructors still differ (WhatsApp receives a built client, Instagram builds its own), and `wappa/domain/` and `wappa/schemas/` still import each other. Each is its own change.
