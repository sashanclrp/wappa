# Package scaffolding

## Contents

- Why one scaffold
- Layers and where each kind of code lives
- The composition root
- Outbound adapter: `wappa/messaging/<platform>/`
- Inbound adapter: `wappa/webhooks/<platform>/`
- Size and naming rules
- How it is enforced

## Why one scaffold

Every Platform adapter has the same shape, so a maintainer who knows one knows all of them, a third Platform copies the tree instead of inventing one, and a responsibility is always in the same file. The layout below is the domain-driven design of Wappa written down: the neutral domain at the center, ports in `wappa/domain/interfaces/`, one adapter package per Platform and direction, and one composition root. When the code and this file disagree, fix one of them in the same change; never let them drift. Splitting a file that has outgrown its shape uses the `refactor-backend-god-files` skill.

## Layers and where each kind of code lives

| Kind | Home | May import |
| --- | --- | --- |
| Neutral values, vocabulary, results, Inbox identity | `wappa/domain/` | stdlib, pydantic, other `wappa/domain/` modules |
| Ports (`IMessenger`, `IMediaLibrary`, caches, readers) | `wappa/domain/interfaces/` | `wappa/domain/` |
| Neutral inbound contract (Universal Webhooks, `BaseMessage`) | `wappa/webhooks/core/` | `wappa/domain/` |
| Platform outbound adapter | `wappa/messaging/<platform>/` | domain, ports, `wappa/messaging/meta/` (Meta Platforms), its own inbound models |
| Platform inbound adapter | `wappa/webhooks/<platform>/` | domain, `wappa/webhooks/core/`, `wappa/core/inbound/` |
| Meta-wide transport and error parsing | `wappa/messaging/meta/` | domain |
| Neutral outbound application code (`OutboundRuntime`, Template transport, the pipeline) | `wappa/messaging/` root and `wappa/core/messaging/` | domain, ports; never a Platform folder |
| Neutral HTTP request and response DTOs | `wappa/schemas/requests/` | domain |
| Composition root | `wappa/platforms/` | everything above |

Platform names, Platform branches and Platform imports are legal only inside the two adapter folders and the composition root. `tests/test_third_platform_contract.py` fails on a Platform branch in shared modules, and `tests/test_platform_scaffold.py` fails when an adapter leaves this scaffold.

## The composition root

```
wappa/platforms/
  __init__.py      # PLATFORMS, BUILTIN_FIELDS, build_platforms, platform_messenger
  entry.py         # PlatformEntry, MessengerDeps, the builder types
  whatsapp.py      # whatsapp_entry(field_registry): wires WhatsApp's inbound and outbound adapters
  instagram.py     # instagram_entry(field_registry)
```

A Platform module is the only place that knows how its adapter is constructed (client, media transport, readers). `__init__.py` lists each Platform's entry function once.

## Outbound adapter: `wappa/messaging/<platform>/`

```
wappa/messaging/<platform>/
  __init__.py            # exports only <Platform>Messenger (the Host-facing Platform Messenger)
  platform_messenger.py  # <Platform>Messenger: self.<platform> on the handler
  client.py              # <Platform>Client: paths and calls over the Platform's transport
  errors.py              # native error -> MessageResult fields; Platform-only codes
  messenger/             # the IMessenger adapter
    __init__.py          # exports <Platform>MessengerAdapter
    adapter.py           # the composed class: __init__, capabilities, supported_operations
    delivery.py          # one send and its result (address fallback, multi-part results)
    text.py              # one mixin module per operation family (ADR-0016)
    media.py
    interactive.py
    specialized.py       # contact, location, requests
    receipts.py          # read receipts and sender actions
    profile.py
  payloads/              # pure wire builders: no I/O, no self
  media/
    rules.py             # what the Platform accepts, refused before I/O, never converted
    library.py           # the IMediaLibrary adapter
    transport.py         # upload, download, CDN fetch
  models/                # Platform wire values and Platform-only values (only when it has any)
  capabilities/          # Platform-only extension interfaces, one module or package each
```

WhatsApp's `capabilities` folder holds its `templates` package (catalog, Template-triggered state; sending stays in the adapter's Template mixins); Instagram's holds `comments.py`, `content.py` and `history.py`. An operation family or transport may take extra modules when it passes the size target (WhatsApp's `media_wire.py`, `template_sends.py`, and its transport's `upload.py`, `download.py`). A Platform without a family leaves its module out; it never adds an empty one for symmetry.

## Inbound adapter: `wappa/webhooks/<platform>/`

```
wappa/webhooks/<platform>/
  __init__.py       # public facade: the Platform's webhook and message types
  fields.py         # the Platform's built-in webhook fields
  models/           # pure wire models (envelope, entries, events); no Universal imports, no I/O
  message_types/    # BaseMessage subclasses, one module per message type
    _base.py        # the Platform's shared message base (identity, ids, timestamps)
    context.py      # the Platform's message context
  routing.py        # route_<platform>_payload: resolves every entry's Inbox (credential I/O allowed)
  processor/        # the PlatformWebhooks adapter: pure translation to Universal Webhooks
    __init__.py     # exports <Platform>WebhookProcessor
    adapter.py      # platform, builtin_fields, route() delegating to routing.py, translate() dispatch
    <lane>.py       # one module per Universal lane or message family
```

The `models` and `message_types` packages never import the `processor` package. The processor is the anti-corruption layer: it is the only module that sees both the Platform's wire shape and the Universal Webhooks.

## Size and naming rules

- A module aims for under about 250 lines, and none passes 450: it becomes a package named after the old file stem. There is no exception list.
- No Platform prefix inside a Platform folder (`wappa/messaging/whatsapp/client.py`, not `whatsapp_client.py`); the class name carries it.
- No `handlers` folder for outbound code (the Handler is the Host's `WappaEventHandler`), and no `utils`, `helpers` or `services`: name a module after what it does.
- No folder that holds one module plus a re-export `__init__.py`, unless the scaffold above names it.
- Code both Meta Platforms repeat goes to `wappa/messaging/meta/`; a value both Platforms use goes to `wappa/domain/`.

## How it is enforced

- `tests/test_platform_scaffold.py` checks each installed Platform's two adapter folders against the required entries above, rejects the banned names, prefixes and one-module folders, keeps pure models from importing the translator, and fails on any module in `wappa/` (except the CLI examples) over 450 lines.
- `tests/test_third_platform_contract.py` keeps Platform branches out of shared code.
- A change that alters the scaffold updates this file, `wappa/messaging/ARCHITECTURE.md` and `wappa/webhooks/ARCHITECTURE.md` "Module Structure", and the root `ARCHITECTURE.md` "Multi-Platform Strategy" in the same commit.

Known layering debt, not yet scaffolded: `wappa/domain/` and `wappa/schemas/` import each other, and `wappa/domain/` still imports `wappa/core/` in a few modules. Merging them is a separate change; don't add new imports in those directions.
