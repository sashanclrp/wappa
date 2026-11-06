---
status: draft
origin: ADR-0025 contract map (2026-11-05)
last_reviewed: 2026-11-06
---

# `IConversationEntryPoints`: starters, menu and welcome on every Platform

## Code reality (2026-11-06)

No equivalent Platform entry-point configuration was found in Wappa or Symphonai. Symphonai Agency conversation starters and agent entry points configure AI behavior, not Meta ice breakers, persistent menus or conversational components. This draft remains separate from the Instagram conversation series.

A shared capability (ADR-0025) that configures how a conversation starts, set once per Inbox:

| Concept | WhatsApp | Instagram | Telegram |
| --- | --- | --- | --- |
| Conversation starters / ice breakers | conversational components: prompts (≤ 4) | ice breakers (≤ 4, question + payload) | — |
| Commands / persistent menu | conversational components: commands (`/cmd` + description) | persistent menu (postback and URL items) | bot commands (`setMyCommands`) + menu button |
| Welcome message | conversational components: welcome message on/off | — (ice breakers act as the welcome) | `/start` handling |

Proposed: `get_entry_points()` and `set_entry_points(EntryPoints(starters, commands, welcome_enabled))`. An adapter maps what its Platform supports and rejects unsupported parts before I/O, per ADR-0025 rule 3. A tap on an Instagram ice breaker already arrives as an interactive selection.

Exit: WhatsApp and Instagram adapters with tests, and a live check that a starter tap reaches `process_message`.
