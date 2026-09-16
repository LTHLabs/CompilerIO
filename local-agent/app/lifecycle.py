from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .main import BuildRecord

TERMINAL_STATUSES = ("SUCCEEDED", "FAILED")
VALIDATION_DIR_PREFIX = "environment-check-"


class BuildJanitor:
    """Retention and cleanup policy for Project Environments and build records."""

    def __init__(self, projects_dir: Path, retention: int) -> None:
        self.projects_dir = projects_dir
        self.retention = max(1, retention)

    def enforce(self, builds: dict[str, BuildRecord]) -> None:
        """Evict the oldest terminal builds (record + project dir) beyond the retention cap.

        Must be called from the build lock so no other build can be running concurrently.
        """
        terminal_ids = [bid for bid, record in builds.items() if record.status in TERMINAL_STATUSES]
        while len(terminal_ids) > self.retention:
            oldest = terminal_ids.pop(0)
            record = builds.get(oldest)
            if record is None:
                continue
            self.safe_delete(record.project_dir)
            del builds[oldest]

    def sweep_startup(self) -> list[str]:
        """Remove every leftover entry under projects_dir; all are orphans after a restart."""
        failures: list[str] = []
        if not self.projects_dir.is_dir():
            return failures
        for entry in self.projects_dir.iterdir():
            if not self.safe_delete(entry):
                failures.append(str(entry))
        return failures

    def cleanup_validation_dirs(self) -> list[str]:
        """Remove environment-check-* directories left over by prepare() runs."""
        failures: list[str] = []
        if not self.projects_dir.is_dir():
            return failures
        for entry in self.projects_dir.iterdir():
            if entry.name.startswith(VALIDATION_DIR_PREFIX):
                if not self.safe_delete(entry):
                    failures.append(str(entry))
        return failures

    def safe_delete(self, path: Path) -> bool:
        """Delete a path inside projects_dir without ever raising; return success."""
        try:
            if not path.parent.resolve() == self.projects_dir.resolve():
                print(f"[BuildJanitor] refusing to delete outside projects_dir: {path}", flush=True)
                return False
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
            return True
        except (OSError, ValueError) as exc:
            print(f"[BuildJanitor] failed to delete {path}: {exc}", flush=True)
            return False
