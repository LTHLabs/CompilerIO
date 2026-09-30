# Local ESP32 Compiler Agent

Run from the workspace root:

```sh
local-agent/venv/bin/python -m uvicorn app.main:app --app-dir local-agent --host 127.0.0.1 --port 8765
```

Set `LOCAL_AGENT_ALLOWED_ORIGINS` to a comma-separated allowlist before connecting a browser. The startup output contains the one-time pairing code. `POST /environment/prepare` must succeed before builds are accepted.

## Execution modes (M2.3)

Supported launcher (binds the address derived from the mode and ignores proxy headers):

```sh
PYTHONPATH=local-agent local-agent/venv/bin/python -m app
```

| Variable | Default | Meaning |
|---|---|---|
| `COMPILERIO_MODE` | `personal` | `personal` or `hub`; any other value refuses to start |
| `COMPILERIO_PORT` | `8765` | Agent port (the Web App assumes 8765) |
| `COMPILERIO_MAX_QUEUED_BUILDS` | `3` | Maximum builds waiting in `QUEUED`; further submissions get HTTP 429 |

**Personal (default)** binds `127.0.0.1` and serves one local user. Requests from non-loopback clients are rejected with 403 even if
uvicorn is started manually on `0.0.0.0`. One one-time pairing code is printed at startup (valid 300 s).

**Hub (explicit opt-in)** binds `0.0.0.0` for several browser clients on a **trusted LAN only** (plain HTTP, no TLS):

```sh
COMPILERIO_MODE=hub \
LOCAL_AGENT_ALLOWED_ORIGINS=http://<hub-lan-ip>:3000,http://localhost:3000 \
PYTHONPATH=local-agent local-agent/venv/bin/python -m app
```

- The agent refuses to start in Hub mode unless `LOCAL_AGENT_ALLOWED_ORIGINS` is set explicitly, names at least one non-loopback
  origin, and contains no wildcard.
- Serve `web-app/` from the Hub host (e.g. `python3 -m http.server 3000 --bind 0.0.0.0 --directory web-app`); clients open
  `http://<hub-lan-ip>:3000` and the Web App connects to `http://<hub-lan-ip>:8765`.
- Pairing: exactly one one-time code is valid at a time. After each successful pairing, and when an unused code expires (300 s),
  a new code is printed in the agent terminal for the next client. Each pairing is a separate session.
- Each session can read only its own builds; other sessions' builds return 404, the same as an unknown build id.
- `/environment/prepare` is host-only in Hub mode: the host operator must open the Web App as `http://localhost:3000` (include that
  origin in the allowlist). Remote clients get 403.
- Builds from all sessions share one queue (one build at a time) and one retention pool.

Do not start uvicorn manually with `--forwarded-allow-ips '*'` (or `FORWARDED_ALLOW_IPS=*`): trusted forwarded headers would let a
remote client appear as loopback. The supported launcher disables proxy headers.

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
