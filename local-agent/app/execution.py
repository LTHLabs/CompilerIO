"""Host-specific execution mechanics for PlatformIO and compiler tools.

EnvironmentManager owns policy (state, Base markers, manifests, readiness, before/after
integrity checks). A backend owns only *how* a command is executed on this host:

- run_offline:   compilation / merge_bin / validation build (no network expected)
- run_networked: dependency preparation (network allowed, hard timeout)
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import Settings


@dataclass(frozen=True)
class ExecResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


class ExecutionBackend(Protocol):
    def check_host(self) -> None:
        """Raise RuntimeError with a user-facing reason if this host cannot run builds."""

    def platformio_env(self) -> dict[str, str]: ...

    def run_offline(self, argv: list[str], cwd: Path) -> ExecResult: ...

    def run_networked(self, argv: list[str], cwd: Path, timeout: int) -> ExecResult: ...


# Shell program run inside the Linux user+mount namespace: bind-mount the Base Environment
# read-only, then bind each Base package/platform read-only over the agent's mutable core dir.
_LINUX_READONLY_MOUNTS = (
    "base=\"$1\"; agent=\"$2\"; shift 2; "
    "mount --bind \"$base\" \"$base\"; mount -o remount,bind,ro \"$base\"; "
    "for source in \"$base/packages\"/*; do "
    "target=\"$agent/packages/${source##*/}\"; "
    "mount --bind \"$source\" \"$target\"; mount -o remount,bind,ro \"$target\"; "
    "done; "
    "mount --bind \"$base/platforms/espressif32\" \"$agent/platforms/espressif32\"; "
    "mount -o remount,bind,ro \"$agent/platforms/espressif32\"; exec \"$@\""
)


class LinuxBackend:
    """Kernel-enforced isolation: user+mount namespaces with read-only Base bind mounts;
    offline runs additionally get an empty network namespace."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def check_host(self) -> None:
        if shutil.which("unshare") is None or shutil.which("mount") is None:
            raise RuntimeError("Linux read-only mount isolation is unavailable.")

    def platformio_env(self) -> dict[str, str]:
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

    def _prepare_mount_targets(self) -> None:
        packages_target = self.settings.agent_core_dir / "packages"
        platforms_target = self.settings.agent_core_dir / "platforms"
        packages_target.mkdir(parents=True, exist_ok=True)
        platforms_target.mkdir(parents=True, exist_ok=True)
        for package in (self.settings.base_environment / "packages").iterdir():
            if package.is_dir():
                (packages_target / package.name).mkdir(exist_ok=True)
        (platforms_target / "espressif32").mkdir(exist_ok=True)

    def _wrap(self, label: str, argv: list[str], network: bool) -> list[str]:
        isolation = ["unshare", "--user", "--map-root-user", "--mount"]
        if not network:
            # The network namespace makes package downloads impossible during build.
            isolation.append("--net")
        return [
            *isolation, "sh", "-ceu", _LINUX_READONLY_MOUNTS,
            label, str(self.settings.base_environment), str(self.settings.agent_core_dir), *argv,
        ]

    def run_offline(self, argv: list[str], cwd: Path) -> ExecResult:
        self._prepare_mount_targets()
        result = subprocess.run(
            self._wrap("readonly-base", argv, network=False),
            env=self.platformio_env(),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        return ExecResult(result.returncode, result.stdout, result.stderr)

    def run_networked(self, argv: list[str], cwd: Path, timeout: int) -> ExecResult:
        self._prepare_mount_targets()
        process = subprocess.Popen(
            self._wrap("readonly-base-net", argv, network=True),
            env=self.platformio_env(),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout_bytes, stderr_bytes = process.communicate(timeout=timeout)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            stdout_bytes = process.stdout.read() if process.stdout else b""
            stderr_bytes = process.stderr.read() if process.stderr else b""
            returncode = -signal.SIGKILL
        return ExecResult(
            returncode,
            stdout_bytes.decode("utf-8", errors="replace"),
            stderr_bytes.decode("utf-8", errors="replace"),
            timed_out,
        )


# PlatformIO progress/log lines that mean a package download or installation happened.
_PACKAGE_ACTIVITY = re.compile(
    r"(?m)^\s*(?:(?:Library|Tool|Platform|Package) Manager:\s*)?(?:Downloading|Installing)\b"
)
OFFLINE_VIOLATION_MESSAGE = (
    "[CompilerIO] Offline phase attempted a package download/installation. "
    "Windows does not isolate the network (detect-only): failing closed."
)


def offline_violation(output: str) -> bool:
    """True if offline-phase output shows PlatformIO downloading or installing a package."""
    return _PACKAGE_ACTIVITY.search(output) is not None


class WindowsBackend:
    """Native Windows execution. No kernel isolation is available here:

    - Base immutability is detect-and-fail-closed (EnvironmentManager manifest before/after).
    - The compile network boundary is detect-only: offline runs fail when PlatformIO output
      shows a download/installation.
    - Base packages/platforms are exposed to PlatformIO through NTFS directory junctions in the
      mutable agent core dir, so PlatformIO lock/state files never land inside the Base.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def check_host(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("The Windows execution backend requires a Windows host.")
        machine = platform.machine().upper()
        if machine not in ("AMD64", "X86_64"):
            raise RuntimeError(f"Unsupported Windows architecture {machine!r}: the esp32dev toolchain requires x64.")
        # Never run on a Base provisioned for another OS (e.g. a copied Linux Base).
        manifest = self.settings.base_environment / "packages" / "toolchain-xtensa-esp32" / "package.json"
        try:
            systems = json.loads(manifest.read_text(encoding="utf-8")).get("system", [])
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Cannot read toolchain package metadata: {manifest}") from exc
        systems = [systems] if isinstance(systems, str) else list(systems)
        if "windows_amd64" not in systems:
            raise RuntimeError(
                f"Base Environment toolchain is not a native Windows build (system={systems}); "
                "provision the Windows Base with local-agent/tools/provision-windows-base.ps1."
            )
        if not self._taskkill().is_file():
            raise RuntimeError(f"taskkill.exe not found at {self._taskkill()}.")

    def platformio_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "PLATFORMIO_CORE_DIR": str(self.settings.agent_core_dir),
                "PLATFORMIO_PACKAGES_DIR": str(self.settings.agent_core_dir / "packages"),
                "PLATFORMIO_PLATFORMS_DIR": str(self.settings.agent_core_dir / "platforms"),
                "PYTHONDONTWRITEBYTECODE": "1",
                # Child processes write UTF-8 regardless of the console code page.
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                # Avoid optional network calls during builds (update checks, telemetry).
                "PLATFORMIO_SETTING_ENABLE_TELEMETRY": "No",
                "PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL": "36500",
            }
        )
        return env

    def _link_base_packages(self) -> None:
        """Expose each Base package/platform in the agent core dir via a directory junction."""
        base = self.settings.base_environment
        pairs = [
            (self.settings.agent_core_dir / "packages", [p for p in (base / "packages").iterdir() if p.is_dir()]),
            (self.settings.agent_core_dir / "platforms", [base / "platforms" / "espressif32"]),
        ]
        for target_root, sources in pairs:
            target_root.mkdir(parents=True, exist_ok=True)
            for source in sources:
                target = target_root / source.name
                if os.path.isjunction(target):
                    if os.path.realpath(target) == os.path.realpath(source):
                        continue
                    os.rmdir(target)  # removes the junction only, never the target contents
                elif target.exists():
                    if target.is_dir() and not any(target.iterdir()):
                        target.rmdir()
                    else:
                        raise RuntimeError(f"Unexpected non-junction entry in agent core dir: {target}")
                import _winapi  # CPython on Windows; creates a junction without admin rights

                _winapi.CreateJunction(str(source), str(target))

    @staticmethod
    def _taskkill() -> Path:
        return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"

    def run_offline(self, argv: list[str], cwd: Path) -> ExecResult:
        self._link_base_packages()
        completed = subprocess.run(
            argv,
            env=self.platformio_env(),
            cwd=cwd,
            capture_output=True,
            check=False,
        )
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        returncode = completed.returncode
        if offline_violation(stdout + stderr):
            stderr += "\n" + OFFLINE_VIOLATION_MESSAGE + "\n"
            returncode = returncode or 1
        return ExecResult(returncode, stdout, stderr)

    def run_networked(self, argv: list[str], cwd: Path, timeout: int) -> ExecResult:
        self._link_base_packages()
        process = subprocess.Popen(
            argv,
            env=self.platformio_env(),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        timed_out = False
        try:
            stdout_bytes, stderr_bytes = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            # Terminate the whole child process tree (pio -> scons/pip/compilers).
            subprocess.run(
                [str(self._taskkill()), "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
                timeout=30,
            )
            try:
                stdout_bytes, stderr_bytes = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout_bytes, stderr_bytes = b"", b"[CompilerIO] output unavailable after timeout kill"
        returncode = process.returncode if process.returncode is not None else 1
        return ExecResult(
            returncode,
            stdout_bytes.decode("utf-8", errors="replace"),
            stderr_bytes.decode("utf-8", errors="replace"),
            timed_out,
        )


class UnsupportedHostBackend:
    """Fails closed on hosts without an execution backend (e.g. macOS, out of scope)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def check_host(self) -> None:
        raise RuntimeError(f"Unsupported host platform for builds: {sys.platform}.")

    def platformio_env(self) -> dict[str, str]:
        raise RuntimeError(f"Unsupported host platform for builds: {sys.platform}.")

    def run_offline(self, argv: list[str], cwd: Path) -> ExecResult:
        raise RuntimeError(f"Unsupported host platform for builds: {sys.platform}.")

    def run_networked(self, argv: list[str], cwd: Path, timeout: int) -> ExecResult:
        raise RuntimeError(f"Unsupported host platform for builds: {sys.platform}.")


def select_backend(settings: Settings) -> ExecutionBackend:
    if sys.platform.startswith("linux"):
        return LinuxBackend(settings)
    if sys.platform == "win32":
        return WindowsBackend(settings)
    return UnsupportedHostBackend(settings)
