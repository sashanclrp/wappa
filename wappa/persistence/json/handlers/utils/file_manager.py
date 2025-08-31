"""
File system operations for JSON cache.

Handles cache directory creation, file I/O, and project root detection.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from .serialization import from_json_string, to_json_string

logger = logging.getLogger("JSONFileManager")


class FileManager:
    """Manages file operations for JSON cache."""

    def __init__(self):
        self._cache_root: Path | None = None
        self._file_locks: dict[str, asyncio.Lock] = {}

    def _get_file_lock(self, file_path: str) -> asyncio.Lock:
        """Get or create a lock for a specific file path."""
        if file_path not in self._file_locks:
            self._file_locks[file_path] = asyncio.Lock()
        return self._file_locks[file_path]

    def get_cache_root(self) -> Path:
        """Get or detect the cache root directory."""
        if self._cache_root is None:
            self._cache_root = self._detect_project_root()
        return self._cache_root

    def _detect_project_root(self) -> Path:
        """
        Detect project root by looking for main.py with Wappa.run().

        Searches from current working directory upwards.
        Falls back to current directory if not found.
        """
        current_dir = Path.cwd()

        # Search upwards for main.py containing Wappa.run()
        for directory in [current_dir] + list(current_dir.parents):
            main_py = directory / "main.py"
            if main_py.exists():
                try:
                    content = main_py.read_text(encoding="utf-8")
                    if "Wappa" in content and (
                        ".run()" in content or "app.run()" in content
                    ):
                        cache_dir = directory / "cache"
                        logger.info(f"Detected project root: {directory}")
                        return cache_dir
                except (OSError, UnicodeDecodeError):
                    continue

        # Fallback to current directory + cache
        fallback_cache = current_dir / "cache"
        logger.info(f"Project root not detected, using fallback: {fallback_cache}")
        return fallback_cache

    def ensure_cache_directories(self) -> None:
        """Create cache directory structure if it doesn't exist."""
        cache_root = self.get_cache_root()
        cache_root.mkdir(exist_ok=True)

        # Create subdirectories
        (cache_root / "users").mkdir(exist_ok=True)
        (cache_root / "tables").mkdir(exist_ok=True)
        (cache_root / "states").mkdir(exist_ok=True)

        logger.debug(f"Cache directories ensured at: {cache_root}")

    def get_cache_file_path(
        self, cache_type: str, tenant_id: str, user_id: str = None
    ) -> Path:
        """
        Get the file path for a cache file.

        Args:
            cache_type: "users", "tables", or "states"
            tenant_id: Tenant identifier
            user_id: User identifier (required for users and states)

        Returns:
            Path to cache file
        """
        cache_root = self.get_cache_root()

        if cache_type == "users":
            if not user_id:
                raise ValueError("user_id is required for users cache")
            return cache_root / "users" / f"{tenant_id}_{user_id}.json"
        elif cache_type == "tables":
            return cache_root / "tables" / f"{tenant_id}_tables.json"
        elif cache_type == "states":
            if not user_id:
                raise ValueError("user_id is required for states cache")
            return cache_root / "states" / f"{tenant_id}_{user_id}_state.json"
        else:
            raise ValueError(f"Invalid cache_type: {cache_type}")

    async def read_file(self, file_path: Path) -> dict[str, Any]:
        """Read and parse JSON file with file locking."""
        async with self._get_file_lock(str(file_path)):
            if not file_path.exists():
                return {}

            try:
                content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
                return from_json_string(content)
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Failed to read file {file_path}: {e}")
                return {}

    async def write_file(self, file_path: Path, data: dict[str, Any]) -> bool:
        """Write data to JSON file with file locking."""
        async with self._get_file_lock(str(file_path)):
            try:
                # Ensure parent directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)

                # Write to temporary file first, then rename (atomic operation)
                temp_file = file_path.with_suffix(file_path.suffix + ".tmp")
                content = to_json_string(data)

                await asyncio.to_thread(temp_file.write_text, content, encoding="utf-8")
                await asyncio.to_thread(temp_file.replace, file_path)

                return True
            except OSError as e:
                logger.error(f"Failed to write file {file_path}: {e}")
                return False

    async def delete_file(self, file_path: Path) -> bool:
        """Delete file with file locking."""
        async with self._get_file_lock(str(file_path)):
            try:
                if file_path.exists():
                    await asyncio.to_thread(file_path.unlink)
                return True
            except OSError as e:
                logger.error(f"Failed to delete file {file_path}: {e}")
                return False

    async def file_exists(self, file_path: Path) -> bool:
        """Check if file exists."""
        return await asyncio.to_thread(file_path.exists)


# Global file manager instance
file_manager = FileManager()
