"""Example project catalog and the interactive ``wappa examples`` menu."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TypedDict

import typer
from rich.console import Console
from rich.table import Table

from .scaffold import _list_existing_user_files

console = Console()


class _ExampleMetadata(TypedDict):
    name: str
    description: str
    features: list[str]
    complexity: str


# Example projects metadata
EXAMPLES: dict[str, _ExampleMetadata] = {
    "init": {
        "name": "Basic Project",
        "description": "Minimal Wappa project with basic message handling",
        "features": ["Message handling", "Mark as read", "Basic response"],
        "complexity": "🟢 Beginner",
    },
    "simple_echo_example": {
        "name": "Simple Echo Bot",
        "description": "Echoes all incoming messages with acknowledgment",
        "features": ["Message echo", "Media handling", "Clean architecture"],
        "complexity": "🟢 Beginner",
    },
    "wappa_expiry_example": {
        "name": "Expiry Triggers Demo",
        "description": "Inactivity detection with message accumulation using Redis expiry triggers",
        "features": [
            "Scheduled event hook",
            "Timer reset pattern",
            "Message accumulation",
            "Batch processing",
        ],
        "complexity": "🟡 Intermediate",
    },
    "scheduled_tasks_example": {
        "name": "Scheduled Tasks Demo",
        "description": "Reminders, reports and heartbeats from a Host scheduler on one hook",
        "features": [
            "Scheduled event hook",
            "APScheduler callback",
            "Prebuilt handler context",
            "Scoped access to another User",
        ],
        "complexity": "🟡 Intermediate",
    },
    "json_cache_example": {
        "name": "JSON Cache Demo",
        "description": "File-based caching with user management and state handling",
        "features": ["JSON caching", "User management", "State handling", "Statistics"],
        "complexity": "🟡 Intermediate",
    },
    "redis_cache_example": {
        "name": "Redis Cache Demo",
        "description": "Redis-powered caching with advanced state management",
        "features": [
            "Redis caching",
            "Advanced state",
            "Performance monitoring",
            "Cache statistics",
        ],
        "complexity": "🟡 Intermediate",
    },
    "openai_transcript": {
        "name": "OpenAI Transcription",
        "description": "Voice message transcription using OpenAI Whisper API",
        "features": ["Audio processing", "OpenAI integration", "Voice transcription"],
        "complexity": "🟡 Intermediate",
    },
    "redis_pubsub_example": {
        "name": "Redis PubSub Plugin",
        "description": "Multi-inbox Redis PubSub with self-subscribing pattern",
        "features": [
            "Redis PubSub",
            "Multi-inbox messaging",
            "Self-subscribing pattern",
            "Channel management",
        ],
        "complexity": "🟡 Intermediate",
    },
    "db_redis_echo_example": {
        "name": "DB + Redis Cache",
        "description": "PostgreSQL + Redis two-tier storage with SOLID architecture",
        "features": [
            "Async PostgreSQL",
            "Redis caching",
            "Conversation persistence",
            "SOLID architecture",
        ],
        "complexity": "🔴 Advanced",
    },
    "wappa_full_example": {
        "name": "Full-Featured Bot",
        "description": "Complete WhatsApp bot with all features and deployment configs",
        "features": [
            "All message types",
            "Media handling",
            "Interactive components",
            "Docker deployment",
        ],
        "complexity": "🔴 Advanced",
    },
}


def _show_examples_menu(target_directory: str) -> None:
    console.print("\n🚀 [bold blue]Wappa Example Projects[/bold blue]")
    console.print("Choose an example to copy to your project:\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="bold")
    table.add_column("Description", style="white")
    table.add_column("Complexity", style="green")
    table.add_column("Key Features", style="yellow")

    example_keys = list(EXAMPLES.keys())
    for i, example in enumerate(EXAMPLES.values(), 1):
        features_text = ", ".join(example["features"][:3])
        if len(example["features"]) > 3:
            features_text += "..."

        table.add_row(
            str(i),
            example["name"],
            example["description"],
            example["complexity"],
            features_text,
        )

    console.print(table)
    console.print("\n")

    while True:
        try:
            choice = typer.prompt(
                f"Enter your choice (1-{len(example_keys)}) or 'q' to quit"
            )

            if choice.lower() == "q":
                console.print("👋 Goodbye!")
                raise typer.Exit(0)

            choice_num = int(choice)
            if 1 <= choice_num <= len(example_keys):
                selected_key = example_keys[choice_num - 1]
                selected_example = EXAMPLES[selected_key]

                console.print(f"\n✨ Selected: [bold]{selected_example['name']}[/bold]")
                console.print(f"📝 Description: {selected_example['description']}")
                console.print(f"🎯 Features: {', '.join(selected_example['features'])}")
                console.print(f"📊 Complexity: {selected_example['complexity']}")

                if typer.confirm(f"\nCopy this example to '{target_directory}'?"):
                    _copy_example(selected_key, target_directory)
                    break
                else:
                    console.print("Selection cancelled. Choose another example:\n")
                    continue

            else:
                console.print(
                    f"❌ Invalid choice. Please enter a number between 1 and {len(example_keys)}"
                )

        except ValueError:
            console.print("❌ Invalid input. Please enter a number or 'q' to quit")
        except KeyboardInterrupt:
            console.print("\n👋 Goodbye!")
            raise typer.Exit(0) from None


def _copy_example(example_key: str, target_directory: str) -> None:
    examples_dir = Path(__file__).parent / "examples"
    source_path = examples_dir / example_key
    target_path = Path(target_directory).resolve()

    if not source_path.exists():
        console.print(f"❌ Example '{example_key}' not found in {examples_dir}")
        raise typer.Exit(1)

    try:
        if target_directory != "." and not target_path.exists():
            target_path.mkdir(parents=True, exist_ok=True)
            console.print(f"📁 Created directory: {target_path}")

        if target_path.exists():
            existing_files = _list_existing_user_files(target_path)

            if existing_files:
                console.print(f"⚠️  Directory {target_path} is not empty:")
                console.print(f"   Found: {[f.name for f in existing_files]}")

                if not typer.confirm("Continue anyway?"):
                    console.print("❌ Example copy cancelled")
                    raise typer.Exit(0)

        console.print(f"🚀 Copying {EXAMPLES[example_key]['name']} to {target_path}")

        for item in source_path.iterdir():
            if item.name in {".git", "__pycache__"}:
                continue

            if item.is_file():
                shutil.copy2(item, target_path / item.name)
                console.print(f"📝 Copied: {item.name}")
            elif item.is_dir():
                shutil.copytree(
                    item,
                    target_path / item.name,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
                console.print(f"📁 Copied: {item.name}/")

        console.print("\n✅ Example copied successfully!")
        console.print("\n📋 Next steps:")
        console.print("1. Navigate to the project directory")
        console.print("2. Install dependencies: uv sync")
        console.print("3. Add your WhatsApp credentials to .env file (if not present)")
        console.print("4. Start development: uv run wappa dev app/main.py")

        if example_key == "redis_cache_example":
            console.print("\n🔧 Redis-specific setup:")
            console.print("   - Install and start Redis server")
            console.print("   - Add REDIS_URL to .env file")
        elif example_key == "wappa_expiry_example":
            console.print("\n🔧 ExpiryActions-specific setup:")
            console.print("   - Install and start Redis server")
            console.print("   - Add REDIS_URL to .env file")
            console.print("   - Redis will auto-configure keyspace notifications")
        elif example_key == "openai_transcript":
            console.print("\n🔧 OpenAI-specific setup:")
            console.print("   - Add LLM_PROVIDER_OPENAI_API_KEY to .env file")
            console.print("   - Ensure audio file handling is configured")

        console.print("\n📖 Check the README.md for detailed setup instructions")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"❌ Failed to copy example: {e}")
        raise typer.Exit(1) from None
