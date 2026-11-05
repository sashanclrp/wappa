# Contributing to Wappa

Thanks for wanting to improve Wappa. This guide gets you set up; [`CODING_STANDARDS.md`](CODING_STANDARDS.md) holds the checks every change passes, the code and test conventions, the documentation each change updates, and the commit format. [`CONTEXT.md`](CONTEXT.md) holds the language Wappa speaks.

## Getting set up

Wappa targets **Python 3.12+** and uses [uv](https://docs.astral.sh/uv/) for dependency management and process launch. Prefer `uv run <cmd>` over `python -m` so everything executes against the locked environment.

```bash
git clone https://github.com/sashanclrp/wappa.git
cd wappa
uv sync --group dev
```

Copy `.env.example` to `.env` and fill in the values you need; it explains every variable and both Inbox Routing Modes.

## Backlog and planning

Larger work is planned in [`docs/backlog/`](docs/backlog/README.md); [`BACKLOG-EXECUTION-PLAN.md`](docs/backlog/BACKLOG-EXECUTION-PLAN.md) orders it. A backlog item lives in `drafts/`, `pending/`, or `in_progress/` depending on how settled it is, and completed items are **deleted** — git history is the archive.

## Security

Never commit secrets. Report a suspected vulnerability privately to the maintainers rather than opening a public issue, and describe the class of problem rather than a working exploit.

## Community and license

- 🐛 Bugs: [GitHub Issues](https://github.com/sashanclrp/wappa/issues)
- 💡 Ideas and questions: [GitHub Discussions](https://github.com/sashanclrp/wappa/discussions)
- 🔰 New here: [good first issues](https://github.com/sashanclrp/wappa/labels/good%20first%20issue)

By contributing you agree that your contributions are licensed under the [Apache License 2.0](LICENSE), the same license that covers Wappa.
