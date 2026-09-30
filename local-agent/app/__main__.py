"""Launch the Local Agent with the bind address derived from COMPILERIO_MODE.

Usage (from the workspace root):
    PYTHONPATH=local-agent local-agent/venv/bin/python -m app

Personal mode (default) binds 127.0.0.1 only. Hub mode binds 0.0.0.0 and must be
selected explicitly with COMPILERIO_MODE=hub plus an explicit LOCAL_AGENT_ALLOWED_ORIGINS.
"""
from __future__ import annotations

import sys

import uvicorn


def main() -> int:
    try:
        from .main import app, settings
    except ValueError as exc:
        # Invalid mode/port or an unsafe Hub configuration: refuse to start.
        print(f"Local Agent refused to start: {exc}", file=sys.stderr, flush=True)
        return 2
    # proxy_headers=False: client address is always the real connection source, so
    # Personal loopback enforcement and Hub host-only prepare cannot be spoofed via X-Forwarded-For.
    uvicorn.run(app, host=settings.host, port=settings.port, proxy_headers=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
