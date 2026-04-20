import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from .serialization import from_json_string, to_json_string

logger = logging.getLogger("JSONFileManager")


class FileManager:
    def __init__(self):
        self._cache_root: Path | None = None
        self._file_locks: dict[str, asyncio.Lock] = {}

    def _get_file_lock(self, file_path: str) -> asyncio.Lock:
        if file_path not in self._file_locks:
            self._file_locks[file_path] = asyncio.Lock()
        return self._file_locks[file_path]

    def get_cache_root(self) -> Path:
        if self._cache_root is None:
            self._cache_root = self._detect_project_root()
        return self._cache_root

    def _detect_project_root(self) -> Path:
        current_dir = Path.cwd()

        for directory in [current_dir, *current_dir.parents]:
            main_py = directory / "main.py"
            if not main_py.exists():
                continue
            try:
                content = main_py.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "Wappa" in content and (".run()" in content or "app.run()" in content):
                cache_dir = directory / "cache"
                logger.info(f"Detected project root: {directory}")
                return cache_dir

        fallback_cache = current_dir / "cache"
        logger.info(f"Project root not detected, using fallback: {fallback_cache}")
        return fallback_cache

    def ensure_cache_directories(self) -> None:
        cache_root = self.get_cache_root()
        cache_root.mkdir(exist_ok=True)
        for sub in ("users", "tables", "states", "ai_states"):
            (cache_root / sub).mkdir(exist_ok=True)
        logger.debug(f"Cache directories ensured at: {cache_root}")

    def get_cache_file_path(
        self, cache_type: str, tenant_id: str, user_id: str | None = None
    ) -> Path:
        cache_root = self.get_cache_root()

        match cache_type:
            case "users":
                if not user_id:
                    raise ValueError("user_id is required for users cache")
                return cache_root / "users" / f"{tenant_id}_{user_id}.json"
            case "tables":
                return cache_root / "tables" / f"{tenant_id}_tables.json"
            case "states":
                if not user_id:
                    raise ValueError("user_id is required for states cache")
                return cache_root / "states" / f"{tenant_id}_{user_id}_state.json"
            case "ai_states":
                if not user_id:
                    raise ValueError("user_id is required for ai_states cache")
                return cache_root / "ai_states" / f"{tenant_id}_{user_id}_ai_state.json"
            case _:
                raise ValueError(f"Invalid cache_type: {cache_type}")

    async def read_file(self, file_path: Path) -> dict[str, Any]:
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
        async with self._get_file_lock(str(file_path)):
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                temp_file = file_path.with_suffix(file_path.suffix + ".tmp")
                content = to_json_string(data)
                await asyncio.to_thread(temp_file.write_text, content, encoding="utf-8")
                await asyncio.to_thread(temp_file.replace, file_path)
                return True
            except OSError as e:
                logger.error(f"Failed to write file {file_path}: {e}")
                return False

    async def delete_file(self, file_path: Path) -> bool:
        async with self._get_file_lock(str(file_path)):
            try:
                if file_path.exists():
                    await asyncio.to_thread(file_path.unlink)
                return True
            except OSError as e:
                logger.error(f"Failed to delete file {file_path}: {e}")
                return False

    async def file_exists(self, file_path: Path) -> bool:
        return await asyncio.to_thread(file_path.exists)


file_manager = FileManager()
