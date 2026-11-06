# Skill routing

Discover skills by name in the current harness, then read the installed source. Never assume a filesystem path.

| Situation | Use | Hand over | Expect back |
| --- | --- | --- | --- |
| Plain Wappa, multi-step flow or Scores | `wappa-conversational-scores` | events to handle, steps, validation, payload scheme | handler and Score code with DI |
| Plain Wappa, cache/Redis/TTL/isolation | `wappa-runtime-state` | what state, lifetime, backends | scoped cache usage and tests |
| Symphonai Host, per-message Score | `symphonai-add-score` | predicate, priority, stop/pass | Symphonai Score |
| Symphonai Host, guided multi-turn form | `symphonai-add-state-handler` | questions, validation, branching | Symphonai StateHandler |
| Symphonai Host, Wappa integration internals | `develop-wappa` | the Wappa surface touched | host adapter guidance |
| Symphonai optional Package or extension | `develop-symphonai-package` | extension scope | Package code |

## Rules

- Plain Wappa must work without any Symphonai skill installed.
- In a Symphonai Host, send with `target=self.deps.user_target` (Scores and StateHandlers) or `self.deps.require_user_target()` (external Scores). Don't reimplement Symphonai's Score engine with plain-Wappa patterns.
- If the right specialist skill is missing, name it and say it ships with Symphonai, then continue on the generic supported path where one exists. Don't invent a path or install packages silently.
- WhatsApp Template work is not Instagram work. Don't run Instagram setup for it; Templates go through `self.whatsapp.templates` or `OutboundRuntime.templates`.
