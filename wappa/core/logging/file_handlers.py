"""Daily-rolling file handler that announces the live file through ``current.log``."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path

from .devserver import point_current_log


def _daily_log_name(day: date) -> str:
    return f"wappa_{day:%Y%m%d}.log"


class DailyFileHandler(logging.FileHandler):
    """Append to ``wappa_YYYYMMDD.log`` and roll over at local midnight.

    Each new file is announced through the ``current.log`` symlink, so a
    reader never has to guess which daily file is live.
    """

    def __init__(self, log_dir: str | os.PathLike[str]) -> None:
        self.log_dir = Path(log_dir)
        self._day = datetime.now().date()
        super().__init__(
            self.log_dir / _daily_log_name(self._day), encoding="utf-8", delay=False
        )
        point_current_log(self.log_dir, self.baseFilename)

    def emit(self, record: logging.LogRecord) -> None:
        today = datetime.fromtimestamp(record.created).date()
        if today != self._day:
            self._roll_to(today)
        super().emit(record)

    def _roll_to(self, day: date) -> None:
        self.acquire()
        try:
            if day == self._day:
                return
            self.close()
            self._day = day
            self.baseFilename = os.path.abspath(self.log_dir / _daily_log_name(day))
            self.stream = self._open()
            point_current_log(self.log_dir, self.baseFilename)
        finally:
            self.release()
