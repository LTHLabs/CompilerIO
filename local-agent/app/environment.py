from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .config import Settings


class EnvironmentState(StrEnum):
    NOT_READY = "NOT_READY"
    PREPARING = "PREPARING"
    READY = "READY"
    ERROR = "ERROR"


@dataclass(frozen=True)
class BaseManifest:
    digest: str
    files: int


class EnvironmentManager:
    """Validates a reusable compiler environment without letting PlatformIO write to it."""

    MARKERS = (
        "platforms/espressif32/platform.json",
        "packages/framework-arduinoespressif32",
        "packages/tool-esptoolpy",
        "packages/tool-scons",
        "packages/toolchain-xtensa-esp32",
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._state = EnvironmentState.NOT_READY
        self._reason = "Environment has not been prepared."
        self._baseline: BaseManifest | None = None

    def status(self) -> dict[str, object]:
        return {
            "status": self._state,
            "reason": self._reason,
            "base_environment": str(self.settings.base_environment),
            "base_environment_verified": self._baseline is not None,
        }

    def prepare(self) -> dict[str, object]:
        if not self._lock.acquire(blocking=False):
            return self.status()
        try:
            self._state = EnvironmentState.PREPARING
            self._reason = "Verifying Base Compiler Environment and write isolation."
            self._validate_base_location()
            self._baseline = self._manifest()
            self._validate_isolated_compile()
            current = self._manifest()
            if current != self._baseline:
                raise RuntimeError("Base Environment changed during validation.")
            self._state = EnvironmentState.READY
            self._reason = "Base Environment and isolated esp32dev build verified."
        except Exception as exc:  # The error is intentionally surfaced through the status endpoint.
            self._state = EnvironmentState.ERROR
            self._reason = str(exc)
        finally:
            self._lock.release()
        return self.status()

    def assert_ready(self) -> None:
        self._assert_ready_manifest()

    def _assert_ready_manifest(self) -> BaseManifest:
        if self._state != EnvironmentState.READY:
            raise RuntimeError(f"Environment is not ready: {self._reason}")
        current = self._manifest()
        if current != self._baseline:
            self._state = EnvironmentState.ERROR
            self._reason = "Base Environment changed after validation."
            raise RuntimeError(self._reason)
        return current

    def platformio_environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "PLATFORMIO_CORE_DIR": str(self.settings.agent_core_dir),
                # These mutable roots contain only lock/state files. Individual Base
                # packages and platforms are bind-mounted read-only beneath them.
                "PLATFORMIO_PACKAGES_DIR": str(self.settings.agent_core_dir / "packages"),
                "PLATFORMIO_PLATFORMS_DIR": str(self.settings.agent_core_dir / "platforms"),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        return env

    def run_platformio(self, project_dir: Path) -> subprocess.CompletedProcess[str]:
        before = self._assert_ready_manifest()
        result = self._run_readonly_base(project_dir)
        if self._manifest() != before:
            self._state = EnvironmentState.ERROR
            self._reason = "Base Environment changed during compilation."
            raise RuntimeError(self._reason)
        return result

    def run_readonly_command(
        self, command: list[str], cwd: Path
    ) -> subprocess.CompletedProcess[str]:
        """Run an arbitrary compiler-tool command with Base packages mounted read-only."""
        before = self._assert_ready_manifest()
        result = self._run_with_readonly_base(command, cwd)
        if self._manifest() != before:
            self._state = EnvironmentState.ERROR
            self._reason = "Base Environment changed during compiler-tool execution."
            raise RuntimeError(self._reason)
        return result

    def _validate_base_location(self) -> None:
        if not self.settings.base_environment.is_dir():
            raise RuntimeError("Base Environment directory is missing.")
        missing = [marker for marker in self.MARKERS if not (self.settings.base_environment / marker).exists()]
        if missing:
            raise RuntimeError(f"Base Environment is incomplete: missing {', '.join(missing)}")
        if not self.settings.python_executable.is_file():
            raise RuntimeError("Local Agent Python executable is missing.")
        if shutil.which("unshare") is None or shutil.which("mount") is None:
            raise RuntimeError("Linux read-only mount isolation is unavailable.")

    def _manifest(self) -> BaseManifest:
        digest = hashlib.sha256()
        files = 0
        for path in sorted(self.settings.base_environment.rglob("*")):
            relative = path.relative_to(self.settings.base_environment).as_posix()
            stat = path.lstat()
            digest.update(f"{relative}\0{stat.st_mode}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode())
            if path.is_file():
                files += 1
        return BaseManifest(digest.hexdigest(), files)

    def _validate_isolated_compile(self) -> None:
        validation_dir = self.settings.projects_dir / f"environment-check-{uuid.uuid4().hex}"
        (validation_dir / "src").mkdir(parents=True, exist_ok=False)
        (validation_dir / "platformio.ini").write_text(
            "[env:esp32dev]\nplatform = espressif32\nboard = esp32dev\nframework = arduino\n",
            encoding="utf-8",
        )
        (validation_dir / "src" / "main.cpp").write_text(
            "#include <Arduino.h>\nvoid setup() { pinMode(2, OUTPUT); }\n"
            "void loop() { digitalWrite(2, !digitalRead(2)); delay(100); }\n",
            encoding="utf-8",
        )
        result = self._run_readonly_base(validation_dir)
        log_path = validation_dir / "platformio.log"
        log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"Isolated esp32dev validation build failed; see {log_path}")
        log = result.stdout + result.stderr
        if "Downloading" in log or "Installing" in log:
            raise RuntimeError("Validation attempted a package download or installation.")
        if not (validation_dir / ".pio" / "build" / "esp32dev" / "firmware.bin").is_file():
            raise RuntimeError("Validation build did not produce firmware.bin.")

    def _run_readonly_base(self, project_dir: Path) -> subprocess.CompletedProcess[str]:
        return self._run_with_readonly_base(
            [
                str(self.settings.python_executable), "-m", "platformio", "run",
                "--project-dir", str(project_dir),
            ],
            project_dir,
        )

    def _run_with_readonly_base(
        self, command_tail: list[str], cwd: Path
    ) -> subprocess.CompletedProcess[str]:
        self._prepare_mount_targets()
        command = [
            # The network namespace makes package downloads impossible during build.
            "unshare", "--user", "--map-root-user", "--mount", "--net", "sh", "-ceu",
            (
                "base=\"$1\"; agent=\"$2\"; shift 2; "
                "mount --bind \"$base\" \"$base\"; mount -o remount,bind,ro \"$base\"; "
                "for source in \"$base/packages\"/*; do "
                "target=\"$agent/packages/${source##*/}\"; "
                "mount --bind \"$source\" \"$target\"; mount -o remount,bind,ro \"$target\"; "
                "done; "
                "mount --bind \"$base/platforms/espressif32\" \"$agent/platforms/espressif32\"; "
                "mount -o remount,bind,ro \"$agent/platforms/espressif32\"; exec \"$@\""
            ),
            "readonly-base", str(self.settings.base_environment), str(self.settings.agent_core_dir), *command_tail,
        ]
        return subprocess.run(
            command,
            env=self.platformio_environment(),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )

    def _prepare_mount_targets(self) -> None:
        packages_target = self.settings.agent_core_dir / "packages"
        platforms_target = self.settings.agent_core_dir / "platforms"
        packages_target.mkdir(parents=True, exist_ok=True)
        platforms_target.mkdir(parents=True, exist_ok=True)
        for package in (self.settings.base_environment / "packages").iterdir():
            if package.is_dir():
                (packages_target / package.name).mkdir(exist_ok=True)
        (platforms_target / "espressif32").mkdir(exist_ok=True)
