# Documentation map

| Kind | One home | What belongs | Naming rule |
| --- | --- | --- | --- |
| Public contract | [docs root](public-contract.md) | Host imports, calls, configuration and observable behavior | `public-contract.md` |
| Decision | [adr/](adr/) | Current decision and trade-off per decision cluster | `NNNN-subject.md`; update the cluster in place |
| Migration guide | [migration/](migration/) | Host upgrade actions and breaking changes | `VERSION.md` for new guides; existing descriptive/versioned names stay valid |
| Platform reference | [platforms/](platforms/) | Native mappings, constraints and source observations | `platform.md`, `platform-topic.md` or shared `topic.md`; `checked_on` for external facts |
| Live evidence | [verification/](verification/) | Dated setup, actions, observations and limits; distinguish offline checks | `YYMMDD-subject.md`, date of first verification |
| Design session record | [design-sessions/](design-sessions/) | Dated questions and answers; link current decisions/contracts | `YYMMDD-subject.md` |
| Engineering request record | [tech-requests/](tech-requests/) | Existing numbered requests and distinct execution traces; historical, not an active queue | `NNN-subject.md`; one record per request |
| Backlog and active plan | [backlog/](backlog/README.md) | Unfinished work, acceptance criteria and execution order | `YYMMDD-urgency-subject.md`, or `YYMMDD-feature/plan.md`; state folders follow the backlog rules |

## Platform references

- [Instagram](platforms/instagram.md): native capability inventory, boundaries and live qualifications.
- [Instagram setup observations](platforms/instagram-setup.md) and [WhatsApp setup observations](platforms/whatsapp-setup.md): dashboard details behind portable setup guidance.
- [Media format evidence](platforms/media-formats.md): raw format/rendering results behind preparation guidance.
- [Rate limits](platforms/rate-limits.md): Meta quotas, codes and observed development-app blocks.

## Authority and upkeep

- Domain language lives in [CONTEXT.md](../CONTEXT.md); [CONTEXT-MAP.md](../CONTEXT-MAP.md) locates context glossaries. Architecture stays beside the code.
- The public contract owns APIs; ADRs own reasons; Platform references own native facts; verification records own dated outcomes. Link between them rather than copy.
- Shipped [Host skills](../wappa/cli/skills/) own portable usage instructions. Platform files identify whether they supply source evidence or supplement those instructions; the maintainer [wappa-develop skill](../.agents/skills/wappa-develop/SKILL.md) owns the change workflow.
- Keep one line per prose paragraph. Preserve historical results, label their date and limitations, and mask account identifiers. Do not teach obsolete snapshots as current behavior.
- Put new unfinished work in the backlog. Merge duplicate records and delete completed plans; git history is the archive. No second session, personal-doc or implementation-plan folder.
