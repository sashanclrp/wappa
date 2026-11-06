"""Project scaffolding for ``wappa init``: templates, skills and file guards."""

from __future__ import annotations

from pathlib import Path

import typer

_SAFE_EXISTING_FILES = frozenset({"pyproject.toml", "uv.lock", "README.md"})


def _get_template_content(template_name: str) -> str:
    template_path = Path(__file__).parent / "templates" / template_name

    if not template_path.exists():
        typer.echo(f"❌ Template not found: {template_name}", err=True)
        raise typer.Exit(1)

    return template_path.read_text()


def _list_existing_user_files(directory: Path) -> list[Path]:
    return [
        path
        for path in directory.iterdir()
        if not path.name.startswith(".") and path.name not in _SAFE_EXISTING_FILES
    ]


SKILLS_SOURCE = Path(__file__).parent / "skills"


def _emit_skills(project_path: Path) -> list[str]:
    """Copy Wappa's developer skills into both discovery lanes.

    ``.claude/skills/<name>`` gets real files; ``.agents/skills/<name>`` is a
    relative symlink to it (identical files where symlinks are unavailable).
    Existing user-owned skill folders are never overwritten.
    """
    import shutil

    if not SKILLS_SOURCE.is_dir():
        return []
    notes: list[str] = []
    for skill in sorted(p for p in SKILLS_SOURCE.iterdir() if p.is_dir()):
        if skill.name.startswith(("_", ".")):
            continue
        claude = project_path / ".claude" / "skills" / skill.name
        agents = project_path / ".agents" / "skills" / skill.name
        if claude.exists() or claude.is_symlink():
            notes.append(f"kept existing .claude/skills/{skill.name}")
        else:
            claude.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(skill, claude, ignore=shutil.ignore_patterns("__pycache__"))
            notes.append(f"created .claude/skills/{skill.name}")
        if agents.exists() or agents.is_symlink():
            notes.append(f"kept existing .agents/skills/{skill.name}")
            continue
        agents.parent.mkdir(parents=True, exist_ok=True)
        try:
            agents.symlink_to(Path("../../.claude/skills") / skill.name)
        except OSError:
            shutil.copytree(claude, agents)
        notes.append(f"linked .agents/skills/{skill.name}")
    return notes


def _initialize_project(directory: str, *, inbox_routing: str = "legacy") -> None:
    project_path = Path(directory).resolve()

    # Check if directory exists, create if it doesn't
    if directory != "." and not project_path.exists():
        try:
            project_path.mkdir(parents=True, exist_ok=True)
            typer.echo(f"📁 Created directory: {project_path}")
        except Exception as e:
            typer.echo(f"❌ Failed to create directory {project_path}: {e}", err=True)
            raise typer.Exit(1) from None

    existing_files = _list_existing_user_files(project_path)

    if existing_files:
        typer.echo(f"⚠️  Directory {project_path} is not empty:", err=True)
        typer.echo(f"   Found: {[f.name for f in existing_files]}", err=True)

        if not typer.confirm("Continue anyway?"):
            typer.echo("❌ Project initialization cancelled")
            raise typer.Exit(1)

    typer.echo(f"🚀 Initializing Wappa project in: {project_path}")

    try:
        (project_path / "app").mkdir(exist_ok=True)
        (project_path / "app" / "scores").mkdir(exist_ok=True)

        typer.echo("📁 Created directory structure")

        explicit = inbox_routing == "explicit"
        templates_to_create = {
            "app/__init__.py": "__init__.py.template",
            "app/main.py": "main.explicit.py.template"
            if explicit
            else "main.py.template",
            "app/master_event.py": "master_event.py.template",
            "app/scores/__init__.py": "__init__.py.template",
            ".gitignore": "gitignore.template",
            ".env": "env.explicit.template" if explicit else "env.template",
        }
        if explicit:
            templates_to_create["app/inbox_directory_source.py"] = (
                "inbox_directory_source.py.template"
            )

        for file_path, template_name in templates_to_create.items():
            full_path = project_path / file_path
            full_path.write_text(_get_template_content(template_name))
            typer.echo(f"📝 Created: {file_path}")

        for note in _emit_skills(project_path):
            typer.echo(f"🧠 Skill: {note}")

        typer.echo()
        typer.echo("✅ Wappa project initialized successfully!")
        typer.echo()
        typer.echo("📋 Next steps:")
        typer.echo("1. Configure .env and the generated Host integration files")
        typer.echo("2. Install dependencies: uv sync")
        typer.echo("3. Start development: uv run wappa dev app/main.py")
        typer.echo()
        typer.echo("🔧 Required environment variables (.env file):")
        typer.echo("   META_APP_SECRET=your_meta_app_secret")
        typer.echo("   WP_WEBHOOK_VERIFY_TOKEN=your_webhook_verify_token")
        if explicit:
            typer.echo("   SYSTEM_INBOX_ROUTING_MODE=explicit")
            typer.echo("   SYSTEM_TOKEN_ENC_KEY=<generated Fernet key>")
            typer.echo("   Implement app/inbox_directory_source.py for Host records")
        else:
            typer.echo("   WP_ACCESS_TOKEN=your_access_token")
            typer.echo("   WP_PHONE_ID=your_phone_id")
            typer.echo("   WP_BID=your_business_id")
        typer.echo()
        typer.echo("📡 Configure this one callback URL in the Meta App:")
        typer.echo("   https://your-domain.com/webhook/inboxes/whatsapp")
        typer.echo(
            "   Wappa authenticates every POST with META_APP_SECRET; "
            "WP_WEBHOOK_VERIFY_TOKEN answers only the GET challenge."
        )

    except Exception as e:
        typer.echo(f"❌ Failed to initialize project: {e}", err=True)
        raise typer.Exit(1) from None
