"""
Wappa CLI main module.

Provides clean command-line interface for development and production workflows.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Wappa WhatsApp Business Framework CLI")
console = Console()

# Example projects metadata
EXAMPLES = {
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
        "name": "Expiry Actions Demo",
        "description": "Inactivity detection with message accumulation using ExpiryActions",
        "features": [
            "ExpiryActions system",
            "Timer reset pattern",
            "Message accumulation",
            "Batch processing",
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
        "description": "Multi-tenant Redis PubSub with self-subscribing pattern",
        "features": [
            "Redis PubSub",
            "Multi-tenant messaging",
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


def _get_template_content(template_name: str) -> str:
    """
    Load template content from the templates directory.

    Args:
        template_name: Name of the template file (e.g., 'main.py.template')

    Returns:
        Template content as string
    """
    template_dir = Path(__file__).parent / "templates"
    template_path = template_dir / template_name

    if not template_path.exists():
        typer.echo(f"❌ Template not found: {template_name}", err=True)
        raise typer.Exit(1)

    return template_path.read_text()


def _initialize_project(directory: str) -> None:
    """
    Initialize a new Wappa project in the specified directory.

    Args:
        directory: Target directory for project initialization
    """
    project_path = Path(directory).resolve()

    # Check if directory exists, create if it doesn't
    if directory != "." and not project_path.exists():
        try:
            project_path.mkdir(parents=True, exist_ok=True)
            typer.echo(f"📁 Created directory: {project_path}")
        except Exception as e:
            typer.echo(f"❌ Failed to create directory {project_path}: {e}", err=True)
            raise typer.Exit(1) from None

    # Check if directory is empty (except for hidden files and common files like pyproject.toml)
    existing_files = [
        f
        for f in project_path.iterdir()
        if not f.name.startswith(".")
        and f.name not in ["pyproject.toml", "uv.lock", "README.md"]
    ]

    if existing_files:
        typer.echo(f"⚠️  Directory {project_path} is not empty:", err=True)
        typer.echo(f"   Found: {[f.name for f in existing_files]}", err=True)

        if not typer.confirm("Continue anyway?"):
            typer.echo("❌ Project initialization cancelled")
            raise typer.Exit(1)

    typer.echo(f"🚀 Initializing Wappa project in: {project_path}")

    try:
        # Create directory structure
        (project_path / "app").mkdir(exist_ok=True)
        (project_path / "app" / "scores").mkdir(exist_ok=True)

        typer.echo("📁 Created directory structure")

        # Create files from templates
        templates_to_create = {
            "app/__init__.py": "__init__.py.template",
            "app/main.py": "main.py.template",
            "app/master_event.py": "master_event.py.template",
            "app/scores/__init__.py": "__init__.py.template",
            ".gitignore": "gitignore.template",
            ".env": "env.template",
        }

        for file_path, template_name in templates_to_create.items():
            full_path = project_path / file_path
            template_content = _get_template_content(template_name)

            full_path.write_text(template_content)
            typer.echo(f"📝 Created: {file_path}")

        typer.echo()
        typer.echo("✅ Wappa project initialized successfully!")
        typer.echo()
        typer.echo("📋 Next steps:")
        typer.echo("1. Add your WhatsApp credentials to .env file")
        typer.echo("2. Install dependencies: uv sync")
        typer.echo("3. Start development: uv run wappa dev app/main.py")
        typer.echo()
        typer.echo("🔧 Required environment variables (.env file):")
        typer.echo("   WP_ACCESS_TOKEN=your_access_token")
        typer.echo("   WP_PHONE_ID=your_phone_id")
        typer.echo("   WP_BID=your_business_id")
        typer.echo("   WHATSAPP_WEBHOOK_VERIFY_TOKEN=your_webhook_verify_token")

    except Exception as e:
        typer.echo(f"❌ Failed to initialize project: {e}", err=True)
        raise typer.Exit(1) from None


def _resolve_module_name(file_path: str) -> tuple[str, Path]:
    """
    Convert a file path to a Python module name and working directory.

    Handles both flat and nested project structures:
        main.py -> ("main", Path("."))
        app/main.py -> ("app.main", Path("."))  # Use dotted import from project root
        examples/redis_demo/main.py -> ("examples.redis_demo.main", Path("."))

    Returns:
        tuple[str, Path]: (module_name, working_directory)
    """
    path = Path(file_path)
    working_dir = Path(".")

    if path.suffix == ".py":
        path = path.with_suffix("")

    module_name = str(path).replace(os.path.sep, ".")

    return module_name, working_dir


def _run_server(
    file_path: str,
    app_var: str,
    host: str,
    port: int,
    workers: int = 1,
    reload: bool = False,
) -> None:
    """
    Run uvicorn server with the specified configuration.

    Shared logic for both development and production server commands.

    Args:
        file_path: Path to the Python file containing the Wappa app
        app_var: Name of the Wappa instance variable
        host: Host address to bind to
        port: Port number to bind to
        workers: Number of worker processes (production only)
        reload: Enable auto-reload (development only)
    """
    if not Path(file_path).exists():
        typer.echo(f"❌ File not found: {file_path}", err=True)
        raise typer.Exit(1)

    module_name, working_dir = _resolve_module_name(file_path)
    import_string = f"{module_name}:{app_var}.asgi"

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        import_string,
        "--host",
        host,
        "--port",
        str(port),
    ]

    if reload:
        cmd.append("--reload")
        mode = "development"
    else:
        cmd.extend(["--workers", str(workers)])
        mode = "production"

    typer.echo(f"🚀 Starting Wappa {mode} server...")
    typer.echo(f"📡 Import: {working_dir / module_name}:{app_var}.asgi")
    typer.echo(f"🌐 Server: http://{host}:{port}")

    if reload:
        typer.echo(f"📝 Docs: http://{host}:{port}/docs")
    else:
        typer.echo(f"👥 Workers: {workers}")

    typer.echo("💡 Press CTRL+C to stop")
    typer.echo()

    try:
        subprocess.run(cmd, check=True, cwd=working_dir)
    except subprocess.CalledProcessError as e:
        typer.echo(
            f"❌ Server failed to start (exit code: {e.returncode})",
            err=True,
        )
        typer.echo("", err=True)
        typer.echo("Common issues:", err=True)
        typer.echo(f"• No module-level '{app_var}' variable in {file_path}", err=True)
        typer.echo(f"• Port {port} already in use", err=True)
        typer.echo(f"• Import errors in {file_path} or its dependencies", err=True)
        typer.echo("", err=True)
        typer.echo(
            f"Make sure your file has: {app_var} = Wappa(...) at module level", err=True
        )
        raise typer.Exit(1) from None
    except KeyboardInterrupt:
        typer.echo("👋 Server stopped")


@app.command()
def dev(
    file_path: str = typer.Argument(
        ..., help="Path to your Python file (e.g., main.py)"
    ),
    app_var: str = typer.Option(
        "app", "--app", "-a", help="Wappa instance variable name"
    ),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
) -> None:
    """
    Run development server with auto-reload.

    Examples:
        wappa dev main.py
        wappa dev examples/redis_demo/main.py --port 8080
        wappa dev src/app.py --app my_wappa_app
    """
    _run_server(file_path, app_var, host, port, reload=True)


@app.command()
def prod(
    file_path: str = typer.Argument(
        ..., help="Path to your Python file (e.g., main.py)"
    ),
    app_var: str = typer.Option(
        "app", "--app", "-a", help="Wappa instance variable name"
    ),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Number of worker processes"
    ),
) -> None:
    """
    Run production server (no auto-reload).

    Examples:
        wappa prod main.py
        wappa prod main.py --workers 4 --port 8080
    """
    _run_server(file_path, app_var, host, port, workers=workers, reload=False)


@app.command()
def init(
    directory: str = typer.Argument(
        ".", help="Directory to initialize (default: current directory)"
    ),
):
    """
    Initialize a new Wappa project.

    Creates a basic Wappa project structure with:
    - app/ directory with main.py and master_event.py
    - scores/ directory (empty)
    - .gitignore file
    - .env template file

    Examples:
        wappa init            # Initialize in current directory
        wappa init my-bot     # Initialize in ./my-bot/ directory
    """
    _initialize_project(directory)


@app.command()
def examples(
    directory: str = typer.Argument(
        ".", help="Directory to copy example to (default: current directory)"
    ),
):
    """
    Browse and copy Wappa example projects.

    Interactive menu to select from various example projects:
    - Basic project template
    - Echo bot example
    - Expiry actions demo (inactivity detection)
    - JSON cache demo
    - Redis cache demo
    - OpenAI transcription
    - Full-featured bot

    Examples:
        wappa examples           # Show examples menu
        wappa examples my-bot    # Copy to ./my-bot/ directory
    """
    _show_examples_menu(directory)


def _show_examples_menu(target_directory: str) -> None:
    """
    Display interactive examples menu and handle selection.

    Args:
        target_directory: Directory to copy the selected example to
    """
    console.print("\n🚀 [bold blue]Wappa Example Projects[/bold blue]")
    console.print("Choose an example to copy to your project:\n")

    # Create examples table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="bold")
    table.add_column("Description", style="white")
    table.add_column("Complexity", style="green")
    table.add_column("Key Features", style="yellow")

    example_keys = list(EXAMPLES.keys())
    for i, (_key, example) in enumerate(EXAMPLES.items(), 1):
        features_text = ", ".join(example["features"][:3])  # Show first 3 features
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

    # Get user selection
    while True:
        try:
            choice = typer.prompt("Enter your choice (1-7) or 'q' to quit")

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
    """
    Copy selected example to target directory.

    Args:
        example_key: Key of the example to copy
        target_directory: Directory to copy to
    """
    examples_dir = Path(__file__).parent / "examples"
    source_path = examples_dir / example_key
    target_path = Path(target_directory).resolve()

    if not source_path.exists():
        console.print(f"❌ Example '{example_key}' not found in {examples_dir}")
        raise typer.Exit(1)

    try:
        # Create target directory if it doesn't exist
        if target_directory != "." and not target_path.exists():
            target_path.mkdir(parents=True, exist_ok=True)
            console.print(f"📁 Created directory: {target_path}")

        # Check if target directory is empty (except for standard files)
        if target_path.exists():
            existing_files = [
                f
                for f in target_path.iterdir()
                if not f.name.startswith(".")
                and f.name not in ["pyproject.toml", "uv.lock", "README.md"]
            ]

            if existing_files:
                console.print(f"⚠️  Directory {target_path} is not empty:")
                console.print(f"   Found: {[f.name for f in existing_files]}")

                if not typer.confirm("Continue anyway?"):
                    console.print("❌ Example copy cancelled")
                    raise typer.Exit(0)

        console.print(f"🚀 Copying {EXAMPLES[example_key]['name']} to {target_path}")

        # Copy all files from the example (including hidden files, excluding .git and __pycache__)
        for item in source_path.iterdir():
            # Skip .git and __pycache__ directories
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

        # Show example-specific instructions
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
            console.print("   - Add OPENAI_API_KEY to .env file")
            console.print("   - Ensure audio file handling is configured")

        console.print("\n📖 Check the README.md for detailed setup instructions")

    except Exception as e:
        console.print(f"❌ Failed to copy example: {e}")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
