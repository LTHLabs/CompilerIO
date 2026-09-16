from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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

    @classmethod
    def from_environment(cls) -> "Settings":
        workspace_root = Path(
            os.environ.get("COMPILERIO_WORKSPACE_ROOT", Path(__file__).resolve().parents[2])
        ).resolve()
        default_origins = "http://localhost:3000,http://127.0.0.1:3000"
        allowed_origins = frozenset(
            origin.strip().rstrip("/")
            for origin in os.environ.get("LOCAL_AGENT_ALLOWED_ORIGINS", default_origins).split(",")
            if origin.strip()
        )
        try:
            build_retention = int(os.environ.get("COMPILERIO_BUILD_RETENTION", "20"))
        except ValueError:
            build_retention = 20
        return cls(
            workspace_root=workspace_root,
            base_environment=(workspace_root / "runtime" / "platformio-data").resolve(),
            agent_core_dir=(workspace_root / "runtime" / "agent-state" / "platformio-core").resolve(),
            projects_dir=(workspace_root / "runtime" / "projects").resolve(),
            # Keep the virtualenv symlink path intact. Resolving it points at the system
            # interpreter and loses the virtualenv's site-packages (including PlatformIO).
            python_executable=workspace_root / "local-agent" / "venv" / "bin" / "python",
            allowed_origins=allowed_origins,
            build_retention=max(1, build_retention),
        )
