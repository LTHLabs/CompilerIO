# CompilerIO — Agent Instructions

## Agent Guardrails

### MVP Scope

In scope:
- ESP32 DevKit V1 (esp32dev board)
- Arduino framework only
- Local compilation via PlatformIO
- Python/FastAPI Local Agent
- Firmware binary generation for manual Wokwi upload

Out of scope (do not implement without explicit approval):
- Cloud compiler/backend
- Database or persistent user storage
- User accounts, login, or authentication beyond pairing tokens
- Automatic Wokwi upload
- macOS support
- Arbitrary multi-board or multi-framework support

### Protected Validated Foundations
The following foundations have been validated and must be preserved. Do not modify them without explicit approval and an appropriate re-validation plan:
- Base environment immutability (SHA-256 manifest in `runtime/platformio-data/`)
- Security model: origin allowlist + one-time pairing code → session token
- Isolation mechanism: `unshare` + read-only bind mounts (Linux user namespaces only)
- Build lifecycle: FIFO eviction of terminal builds, startup sweep, validation dir cleanup
- Firmware generation: `esptool.py merge_bin` at fixed offsets (0x1000/0x8000/0x10000)
- PlatformIO config template: espressif32 + esp32dev + arduino

### Inspect-Before-Modify

Before any code change:
1. Read the relevant source file(s) in `local-agent/app/`
2. Understand existing conventions: imports, error patterns, naming, async usage
3. Check module boundaries: `main.py` (routes), `environment.py` (build/isolation), `security.py` (auth), `lifecycle.py` (retention), `config.py` (settings)
4. Verify no duplicate logic exists before adding new

### High-Risk Changes Requiring Explicit Approval

Require explicit user approval before modifying:
- Security/authentication/pairing logic (`security.py`, pairing flow)
- Environment isolation mechanism (`environment.py`, unshare/mount usage)
- Base Environment handling: provisioning, validation, manifest generation
- Build pipeline: PlatformIO invocation, `merge_bin`, artifact collection (`environment.py`)
- API contract: endpoints, headers, request/response schemas (`main.py`)
- Build lifecycle/retention logic (`lifecycle.py`)
- Project architecture: module boundaries, data flow, dependency direction
- Validated integrity mechanisms: SHA-256 manifest, immutability checks

### Measure-Before-Optimize

- No performance optimization without baseline from `Eksperiment/validation/`
- Benchmark numbers in documentation are stale; always re-measure on target host
- Do not cite or hardcode specific timing/disk figures in code or docs

### Validation-Before-Declaring-Complete

For any implementation change:

- Preserve all existing security/integrity guarantees
- Validate affected functionality against relevant validation reports in `Eksperiment/validation/`
- Run appropriate tests or validation for the affected subsystem when applicable
- Verify no unintended changes to Protected Validated Foundations
- Do not invent a universal checklist — use subsystem-appropriate validation
### Source-of-Truth Priority

When information conflicts, use this order according to the type of information:

1. Current source code (`local-agent/app/`) — actual implementation
2. Product Requirements Document (PRD) — product requirements and intended scope
3. Newest validation report (`Eksperiment/validation/`) — validated behavior and evidence
4. Older experiment reports (`Eksperiment/validation/`)
5. README — project usage and documentation
6. AGENTS.md — agent workflow and guardrails
7. Code comments
8. Agent assumptions

When runtime behavior differs from the documented implementation,
treat the runtime result as evidence of the current behavior and
investigate the discrepancy before changing the system.

## Technical Reference

## Running the Local Agent

```bash
# From workspace root
local-agent/venv/bin/python -m uvicorn app.main:app --app-dir local-agent --host 127.0.0.1 --port 8765
```

### Required Environment Variables
- `LOCAL_AGENT_ALLOWED_ORIGINS` — comma-separated allowlist (default: `http://localhost:3000,http://127.0.0.1:3000`)
- `COMPILERIO_WORKSPACE_ROOT` — optional, defaults to repo root
- `COMPILERIO_BUILD_RETENTION` — max terminal builds to keep (default: 20, min: 1)

### Startup Output
On startup, agent prints a one-time pairing code (valid 300s). Browser must POST `/session/pair` with this code to get a session token.

## Key API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/environment/status` | — | Check base environment readiness |
| POST | `/environment/prepare` | origin + token | Provision/validate base env (run once) |
| POST | `/session/pair` | origin | Exchange pairing code for session token |
| POST | `/build` | origin + token | Submit source code for compilation |
| GET | `/build/{id}/status` | origin + token | Poll build status |
| GET | `/build/{id}/log` | origin + token | Get full compiler log |
| GET | `/build/{id}/firmware/{name}` | origin + token | Download firmware artifact |

### Required Headers for Protected Endpoints
- `Origin` — must be in allowlist
- `x-local-agent-token` — session token from `/session/pair`

## Build Flow
1. `POST /environment/prepare` → must return `"status": "READY"` before builds accepted
2. `POST /build` with `{source_code, board: "esp32dev", framework: "arduino"}` → returns `build_id`
3. Poll `GET /build/{id}/status` until `SUCCEEDED` or `FAILED`
4. On success: `GET /build/{id}/firmware/wokwi-firmware.bin` for Wokwi upload

## Security Model
- **Origin allowlist**: Only configured origins can connect
- **Session token**: One-time pairing code → token; token required for all build operations
- **No cloud auth**: Everything runs locally

## Environment Isolation (Linux only)
Agent uses `unshare` + read-only bind mounts to prevent PlatformIO from modifying the shared base environment (`runtime/platformio-data/`). Each build gets a fresh project directory under `runtime/projects/{build_id}/`.

**Requires**: Linux with `unshare` and `mount` (user namespaces). Not supported on macOS/Windows natively.

## Build Retention & Cleanup
- FIFO eviction of terminal builds (`SUCCEEDED` + `FAILED`) beyond `COMPILERIO_BUILD_RETENTION`
- Eviction removes: build record, project directory, firmware artifacts
- `QUEUED`/`RUNNING` builds never evicted
- On agent restart: all previous project dirs swept (API returns 404)
- `environment-check-*` validation dirs cleaned after successful `/environment/prepare`

## Development Notes

### Python Dependencies
```
fastapi>=0.115,<1
uvicorn>=0.30,<1
```
Installed in `local-agent/venv/`

### Directory Structure
```
local-agent/
  app/
    main.py         # FastAPI app, build orchestration
    config.py       # Settings from env vars
    environment.py  # Base env validation, read-only isolation, PlatformIO execution
    security.py     # Origin allowlist, pairing code, session tokens
    lifecycle.py    # Build retention, startup sweep, cleanup
  venv/             # Virtual environment (gitignored)
runtime/            # Runtime state (gitignored)
  platformio-data/  # Base compiler environment (protected)
  agent-state/      # PlatformIO core dir (locks, mutable state)
  projects/         # Per-build project directories
Eksperiment/        # Validation/profiling logs (not for production)
```

### PlatformIO Config (generated per build)
```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
```

### Firmware Generation
After PlatformIO build, `esptool.py merge_bin` creates `wokwi-firmware.bin`:
```
bootloader.bin @ 0x1000
partitions.bin @ 0x8000
firmware.bin   @ 0x10000
```

## Testing / Validation
Validation reports in `Eksperiment/validation/` document build behavior, timing, and environment integrity. Key findings:
- Base environment immutable (verified via SHA-256 manifest)
- Firmware non-deterministic (timestamps/paths embedded) — sizes stable, hashes differ
- Quantitative benchmarks (build time, disk usage, environment size) vary by host and cache state. See `Eksperiment/validation/` for current measurements. Do not hardcode or cite specific numbers here.

## Common Tasks

Before modifying: read the relevant module and inspect existing patterns.

### Add a new API endpoint
1. Add route in `main.py`
2. Use `Depends(protected)` for auth
3. Follow existing patterns for error handling

### Modify build retention
Set `COMPILERIO_BUILD_RETENTION` env var at startup.

### Debug environment issues
- Check `GET /environment/status`
- Review `platformio.log` in project directory
- Verify `unshare`/`mount` available on host

### Update allowed origins
Set `LOCAL_AGENT_ALLOWED_ORIGINS` before starting agent.