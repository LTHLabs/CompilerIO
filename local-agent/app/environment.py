from __future__ import annotations

import hashlib
import threading
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .config import Settings
from .execution import ExecResult, ExecutionBackend, select_backend


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

    def __init__(self, settings: Settings, backend: ExecutionBackend | None = None) -> None:
        self.settings = settings
        # Host-specific execution mechanics (Linux namespaces / Windows native); policy stays here.
        self.backend = backend if backend is not None else select_backend(settings)
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
        return self.backend.platformio_env()

    def run_platformio(self, project_dir: Path) -> ExecResult:
        before = self._assert_ready_manifest()
        result = self._run_platformio_offline(project_dir)
        if self._manifest() != before:
            self._state = EnvironmentState.ERROR
            self._reason = "Base Environment changed during compilation."
            raise RuntimeError(self._reason)
        return result

    def run_readonly_command(self, command: list[str], cwd: Path) -> ExecResult:
        """Run an offline compiler-tool command; the Base must be unchanged afterwards."""
        before = self._assert_ready_manifest()
        result = self.backend.run_offline(command, cwd)
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
        self.backend.check_host()

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
        result = self._run_platformio_offline(validation_dir)
        log_path = validation_dir / "platformio.log"
        log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"Isolated esp32dev validation build failed; see {log_path}")
        log = result.stdout + result.stderr
        if "Downloading" in log or "Installing" in log:
            raise RuntimeError("Validation attempted a package download or installation.")
        if not (validation_dir / ".pio" / "build" / "esp32dev" / "firmware.bin").is_file():
            raise RuntimeError("Validation build did not produce firmware.bin.")

    def _run_platformio_offline(self, project_dir: Path) -> ExecResult:
        return self.backend.run_offline(
            [
                str(self.settings.python_executable), "-m", "platformio", "run",
                "--project-dir", str(project_dir),
            ],
            project_dir,
        )

    def prepare_dependencies(self, project_dir: Path, timeout_seconds: int) -> ExecResult:
        """Install project dependencies (network allowed) with a hard timeout."""
        before = self._assert_ready_manifest()
        result = self.backend.run_networked(
            [
                str(self.settings.python_executable), "-m", "platformio", "pkg", "install",
                "--project-dir", str(project_dir),
                "--environment", "esp32dev",
            ],
            project_dir,
            timeout_seconds,
        )
        if self._manifest() != before:
            self._state = EnvironmentState.ERROR
            self._reason = "Base Environment changed during dependency preparation."
            raise RuntimeError(self._reason)
        return result
