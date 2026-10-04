from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

PERSONAL_MODE = "personal"
HUB_MODE = "hub"
MODE_HOSTS = {PERSONAL_MODE: "127.0.0.1", HUB_MODE: "0.0.0.0"}


def is_loopback_host(host: str | None) -> bool:
    """True for localhost names and loopback IPs (including IPv4-mapped IPv6)."""
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback


@dataclass(frozen=True)
class Settings:
    workspace_root: Path
    base_environment: Path
    agent_core_dir: Path
    projects_dir: Path
    python_executable: Path
    allowed_origins: frozenset[str]
    pairing_ttl_seconds: int = 300
    build_retention: int = 20
    dependency_prepare_timeout: int = 180
    # Maximum number of builds in QUEUED status (waiting for build_lock). The active build is not counted.
    max_queued_builds: int = 3
    # Execution mode. Personal (default) serves only loopback clients; Hub is an explicit opt-in.
    mode: str = PERSONAL_MODE
    port: int = 8765

    @property
    def host(self) -> str:
        """Bind address is derived from the mode and is intentionally not configurable."""
        return MODE_HOSTS[self.mode]

    @classmethod
    def from_environment(cls) -> "Settings":
        workspace_root = Path(
            os.environ.get("COMPILERIO_WORKSPACE_ROOT", Path(__file__).resolve().parents[2])
        ).resolve()
        mode = os.environ.get("COMPILERIO_MODE", PERSONAL_MODE).strip().lower()
        if mode not in MODE_HOSTS:
            raise ValueError(f"COMPILERIO_MODE must be '{PERSONAL_MODE}' or '{HUB_MODE}', got {mode!r}.")
        try:
            port = int(os.environ.get("COMPILERIO_PORT", "8765"))
        except ValueError as exc:
            raise ValueError("COMPILERIO_PORT must be an integer.") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"COMPILERIO_PORT must be between 1 and 65535, got {port}.")
        default_origins = "http://localhost:3000,http://127.0.0.1:3000"
        explicit_origins = os.environ.get("LOCAL_AGENT_ALLOWED_ORIGINS")
        allowed_origins = frozenset(
            origin.strip().rstrip("/")
            for origin in (explicit_origins or default_origins).split(",")
            if origin.strip()
        )
        if mode == HUB_MODE:
            # Hub mode is reachable from the LAN: refuse to start without an explicit allowlist
            # that names at least one non-loopback origin. Wildcards are never accepted.
            if explicit_origins is None or not allowed_origins:
                raise ValueError("Hub mode requires LOCAL_AGENT_ALLOWED_ORIGINS to be set explicitly.")
            if any("*" in origin for origin in allowed_origins):
                raise ValueError("Hub mode does not accept wildcard origins.")
            if all(is_loopback_host(urlparse(origin).hostname) for origin in allowed_origins):
                raise ValueError("Hub mode requires at least one non-loopback origin in LOCAL_AGENT_ALLOWED_ORIGINS.")
        try:
            build_retention = int(os.environ.get("COMPILERIO_BUILD_RETENTION", "20"))
        except ValueError:
            build_retention = 20
        try:
            max_queued_builds = int(os.environ.get("COMPILERIO_MAX_QUEUED_BUILDS", "3"))
        except ValueError:
            max_queued_builds = 3
        try:
            dependency_prepare_timeout = int(os.environ.get("COMPILERIO_DEPENDENCY_PREPARE_TIMEOUT", "180"))
        except ValueError:
            dependency_prepare_timeout = 180
        return cls(
            workspace_root=workspace_root,
            base_environment=(workspace_root / "runtime" / "platformio-data").resolve(),
            agent_core_dir=(workspace_root / "runtime" / "agent-state" / "platformio-core").resolve(),
            projects_dir=(workspace_root / "runtime" / "projects").resolve(),
            # Keep the virtualenv symlink path intact. Resolving it points at the system
            # interpreter and loses the virtualenv's site-packages (including PlatformIO).
            python_executable=(
                workspace_root / "local-agent" / "venv" / "Scripts" / "python.exe"
                if os.name == "nt"
                else workspace_root / "local-agent" / "venv" / "bin" / "python"
            ),
            allowed_origins=allowed_origins,
            build_retention=max(1, build_retention),
            max_queued_builds=max(1, max_queued_builds),
            dependency_prepare_timeout=max(1, dependency_prepare_timeout),
            mode=mode,
            port=port,
        )
