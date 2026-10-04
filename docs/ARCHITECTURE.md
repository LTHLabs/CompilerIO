# CompilerIO — Architecture (stable)

Requirements live in the PRD and guardrails in `AGENTS.md`. This file describes how the system is built.
Statements below are CODE VERIFIED unless marked otherwise; runtime evidence is in `docs/PROJECT_STATE.md`.

## Flow
```
Web App (static ES modules, browser)
  → Local Agent (FastAPI, port 8765; Personal binds 127.0.0.1, Hub binds 0.0.0.0 — see Execution modes)
    → Project Environment  runtime/projects/<build_id>/
      → PlatformIO (uses the Base Environment, read-only)
        → esptool merge_bin → wokwi-firmware.bin
          → manual upload to Wokwi
```

## Local Agent modules (`local-agent/app/`)
| Module | Role |
|---|---|
| `main.py` | Routes, `BuildRequest`, build orchestration (`run_build`, `write_project`, `merge_firmware`), Personal loopback middleware, build ownership, queue admission |
| `environment.py` | Policy: Base markers, SHA-256 manifest, READY/ERROR state, validation build, before/after integrity checks around every execution |
| `execution.py` | Host execution backends behind `ExecutionBackend` (`check_host`, `platformio_env`, `run_offline`, `run_networked` → `ExecResult` with `timed_out`) |
| `dependency_validator.py` | `lib_deps` validation (Registry-only) |
| `security.py` | Origin allowlist, one-time pairing codes → per-session token (`token → session_id`, in memory) |
| `lifecycle.py` | Build retention (FIFO), startup sweep, validation-dir cleanup |
| `config.py` | Settings from environment variables, execution mode, Hub startup guard |
| `__main__.py` | Supported launcher (`python -m app`): binds the mode's address, `proxy_headers=False` |

## Execution modes (M2.3)
`COMPILERIO_MODE` selects the mode at startup; the bind address is derived from it and is not configurable.

| | Personal (default) | Hub (explicit opt-in) |
|---|---|---|
| Launcher bind | `127.0.0.1:8765` | `0.0.0.0:8765` |
| Accepted clients | loopback only — non-loopback requests get 403 from middleware, even if uvicorn is bound to 0.0.0.0 manually | any client whose `Origin` is in the explicit allowlist |
| Startup requirement | none | refuses to start unless `LOCAL_AGENT_ALLOWED_ORIGINS` is set explicitly, contains a non-loopback origin and no wildcard |
| Pairing | one one-time code per agent start (valid 300 s) | exactly one valid one-time code at a time; replaced after each successful pairing and when it expires unused |
| `/environment/prepare` | the paired local client | host-only: loopback connection source required, else 403 (checked before `build_lock`) |

Hub mode is intended for a **trusted LAN only**: traffic is plain HTTP.

- **Sessions:** every successful pairing creates a distinct `session_id` and token (in memory; cleared on restart).
- **Build ownership:** each `BuildRecord` stores the creating `session_id`; status/log/firmware for a build owned by
  another session return the same `404 {"detail":"Build not found."}` as an unknown `build_id`.
- **Queue:** the existing `asyncio.Lock` (`build_lock`) serializes builds and `/environment/prepare` (FIFO, one at a time).
  `create_build` rejects with 429 once `COMPILERIO_MAX_QUEUED_BUILDS` (default 3) builds are `QUEUED`; the active build is not
  counted. The limit and retention are global across sessions.
- **Host detection:** loopback is judged from the TCP connection source. The launcher disables uvicorn proxy headers so it cannot be
  spoofed with `X-Forwarded-For`.

## Base vs Project Environment
- **Base Environment** (`runtime/platformio-data/`): shared, immutable compiler platform and packages (espressif32, framework, toolchain, esptool, scons).
  Guarded by a SHA-256 manifest (relative path, mode, size, mtime) taken at `/environment/prepare` and re-checked before and after each
  dependency, compile and merge phase. A mismatch puts the environment in ERROR.
- **Project Environment** (`runtime/projects/<build_id>/`): one fresh directory per build with `platformio.ini`, `src/main.cpp`, `.pio/`
  (including `.pio/libdeps/esp32dev/` and build outputs). Removed by retention eviction or the startup sweep.
- `runtime/agent-state/platformio-core/`: PlatformIO core dir (locks and state). Base packages and the platform are bind-mounted
  read-only beneath it for each run.

## Build phases and network boundary
Order in `run_build`: validate `lib_deps` → write project → **dependency preparation** → **compile** → `merge_bin`.

| Phase | Isolation | Network |
|---|---|---|
| Dependency preparation (`LinuxBackend.run_networked`) | `unshare --user --map-root-user --mount`, Base bind-mounted read-only, own process group, hard timeout with `killpg(SIGKILL)` | **ON** |
| Compile and `merge_bin` (`LinuxBackend.run_offline`) | same wrapper plus `--net` | **OFF** |

Isolation needs Linux user namespaces (`unshare`, `mount`).

**Host backends (M2.4).** `select_backend` picks the backend from the host OS; any other OS fails closed.
- **Linux (`LinuxBackend`) — RUNTIME validated:** kernel-enforced isolation as in the table above (read-only bind mounts,
  empty network namespace for offline runs, process-group kill on dependency timeout).
- **Windows (`WindowsBackend`) — implemented, NOT validated on a real Windows host (M2.4 G1/G3 blocked):** native execution
  without kernel isolation. The Base is exposed through NTFS directory junctions in the agent core dir, so PlatformIO's lock files
  stay outside the Base. Base integrity is detect-and-fail-closed (the manifest checks before/after). The compile network boundary is
  **detect-only**: an offline run fails if PlatformIO output shows `Downloading`/`Installing`. A timeout kills the process tree
  with `taskkill /T /F`. A Base whose toolchain is not a `windows_amd64` build is refused. This is weaker than Linux: nothing
  prevents writes or network access, they are only detected. The native Windows Base is provisioned with
  `local-agent/tools/provision-windows-base.ps1` (pinned versions); the Linux Base is never copied.

## Dependency contract
- `platformio.ini` is the **only** dependency manifest. `write_project` writes `lib_deps` there; dependency preparation runs
  `python -m platformio pkg install --project-dir <dir> --environment esp32dev`, which reads the ini and installs into
  `<project>/.pio/libdeps/esp32dev/`, including transitive dependencies. No second dependency list exists.
- PlatformIO Registry only, owner-qualified: `owner/name@version`. The validator rejects ownerless specs, URL/git/`file://` specs,
  and absolute or relative paths. Exact versions are used; `^` ranges are currently rejected by the validator.
- Reason for the owner requirement: PlatformIO skips ownerless specs during project dependency installation, so they would
  fail later at the offline compile.

## Data flow of `lib_deps`
```
Web App state:  selectedLibDeps = [{ header, platformioName }, ...]      (object[])
  build.js:     selectedLibDeps.map(dep => dep.platformioName)
API payload:    { source_code, board, framework, lib_deps: ["owner/name@x.y.z", ...] }   (string[])
Agent:          BuildRequest.lib_deps: list[str] → validate_lib_deps → platformio.ini
```
`web-app/library-catalog.js` holds `LIBRARY_CATALOG` (header → `{name, platformioName, verifiedAt, verifiedBy}`),
imported by `web-app/library.js`. An entry is added only after a build-verified run (Registry-only, owner-qualified,
exact version, matching `dependency_validator.py`). A detected external header with no catalog entry is classified
`unknown`: `resolveLibrary` returns `platformioName: null`, and `renderLibraryPanel` renders no Add button for it, so
it cannot enter `selectedLibDeps` or the `/build` payload. Currently only `DHT.h` is in the catalog; see
`docs/PROJECT_STATE.md` for the status of the rest.

## Web App
Static ES modules loaded from `index.html` via `app.js` (`state.js` store and `AppState`, `api.js`, `editor.js`,
`library.js`, `pairing.js`, `prepare.js`, `build.js`, `logger.js`, `wokwi.js`). It talks only to the Local Agent.
Allowed origins default to `http://localhost:3000` and `http://127.0.0.1:3000`.

Agent address (`api.js`): default `http://<page hostname>:8765` (page at `localhost` → local agent; page loaded from the Hub
host → that host's agent), falling back to `http://127.0.0.1:8765`. An agent URL stored at pairing time (`sessionStorage`
`compilerio_agent_url`, from the `#agentUrl` field) takes precedence; that field is `readonly` in `index.html`.
CSP `connect-src` is `http://127.0.0.1:8765 http://localhost:8765 http://*:8765` — any host, but only `http:` on port 8765.
The agent port 8765 is assumed by both `api.js` and the CSP.

## Security
Origin allowlist plus one-time pairing code → per-session token (`x-local-agent-token`), with per-session build ownership
(see Execution modes). No cloud, database, accounts or roles. Not implemented: TLS, token expiry, pairing rate limiting,
mDNS/discovery, tunnelling, Internet exposure.

## Runtime layout (gitignored)
```
runtime/
  platformio-data/   Base Environment (protected, read-only during runs)
  agent-state/       PlatformIO core dir (locks, mutable state; base packages mounted read-only over it)
  projects/          per-build project dirs (and environment-check-* during prepare)
```
Firmware artifacts stay under `runtime/projects/<build_id>/.pio/build/esp32dev/` and are served by the agent.
