# CompilerIO — Architecture (stable)

Requirements live in the PRD and guardrails in `AGENTS.md`. This file describes how the system is built.
Statements below are CODE VERIFIED unless marked otherwise; runtime evidence is in `docs/PROJECT_STATE.md`.

## Flow
```
Web App (static ES modules, browser)
  → Local Agent (FastAPI, 127.0.0.1:8765)
    → Project Environment  runtime/projects/<build_id>/
      → PlatformIO (uses the Base Environment, read-only)
        → esptool merge_bin → wokwi-firmware.bin
          → manual upload to Wokwi
```

## Local Agent modules (`local-agent/app/`)
| Module | Role |
|---|---|
| `main.py` | Routes, `BuildRequest`, build orchestration (`run_build`, `write_project`, `merge_firmware`) |
| `environment.py` | Base Environment validation, isolation wrappers, dependency preparation, PlatformIO execution |
| `dependency_validator.py` | `lib_deps` validation (Registry-only) |
| `security.py` | Origin allowlist, pairing code → session token |
| `lifecycle.py` | Build retention (FIFO), startup sweep, validation-dir cleanup |
| `config.py` | Settings from environment variables |

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
| Dependency preparation (`_run_dependency_preparation`) | `unshare --user --map-root-user --mount`, Base bind-mounted read-only, own process group, hard timeout with `killpg(SIGKILL)` | **ON** |
| Compile and `merge_bin` (`_run_with_readonly_base`) | same wrapper plus `--net` | **OFF** |

Isolation needs Linux user namespaces (`unshare`, `mount`).

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

## Security
Origin allowlist plus one-time pairing code → session token (`x-local-agent-token`). No cloud, database or accounts (see `AGENTS.md`).

## Runtime layout (gitignored)
```
runtime/
  platformio-data/   Base Environment (protected, read-only during runs)
  agent-state/       PlatformIO core dir (locks, mutable state; base packages mounted read-only over it)
  projects/          per-build project dirs (and environment-check-* during prepare)
```
Firmware artifacts stay under `runtime/projects/<build_id>/.pio/build/esp32dev/` and are served by the agent.
