# Local ESP32 Compiler Agent

Run from the workspace root:

```sh
local-agent/venv/bin/python -m uvicorn app.main:app --app-dir local-agent --host 127.0.0.1 --port 8765
```

Set `LOCAL_AGENT_ALLOWED_ORIGINS` to a comma-separated allowlist before connecting a browser. The startup output contains the one-time pairing code. `POST /environment/prepare` must succeed before builds are accepted.

## Build retention and cleanup

`COMPILERIO_BUILD_RETENTION` limits how many recent builds are kept on disk and in memory (default: 20). Override it as an environment variable when starting the agent:

```sh
COMPILERIO_BUILD_RETENTION=3 local-agent/venv/bin/python -m uvicorn app.main:app --app-dir local-agent --host 127.0.0.1 --port 8765
```

- Retention is count-based and FIFO over a single pool of terminal builds — `SUCCEEDED` and `FAILED` together.
- Eviction is coupled: the `BuildRecord`, project directory, and firmware artifacts of the oldest terminal build are removed together, so status, log, and firmware endpoints return 404 for the evicted build.
- `QUEUED` and `RUNNING` builds are never evicted.
- Minimum effective value is 1: values below 1 are clamped to 1, and non-integer values fall back to the default of 20.
- After an agent restart, all previous project directories are swept at startup, so every build from before the restart is API-dead (404).
- `environment-check-*` validation directories are removed automatically after a successful `/environment/prepare`.
- Cleanup failures never crash the agent; failed paths are reported on stdout and are swept again on the next startup.
- Disk usage is bounded at roughly retention × ~9 MB per build (≈ 184 MB at the default of 20).
