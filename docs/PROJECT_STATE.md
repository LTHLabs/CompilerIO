# CompilerIO — Project State (live handoff)

Update when a gate finishes: replace items, do not append history. Source code beats this file.
Labels: **CODE** = read in source, **RUNTIME** = observed in a real run. No timing/benchmark figures here (see `AGENTS.md`).

## Snapshot
- Date: 2026-10-01. Branch `milestone-2-library-handling`, HEAD `ccbcc91` (M2.3 committed).
- Uncommitted: **M2.4 Windows Support (in progress)** — new `local-agent/app/execution.py` and
  `local-agent/tools/provision-windows-base.ps1`; modified `environment.py`, `main.py`, `config.py`, `docs/ARCHITECTURE.md`, this file;
  report `Eksperiment/validation/m2.4-validation-2026-09-30.md`. No `.github/workflows` and no git remote exist yet.
- M2.4 status: see "M2.4 Evidence Contract" below. Windows is implemented but not validated on any Windows host (CI or physical);
  do not claim Windows support.
- `CLAUDE.md` (root) and `docs/AGENTS.md` are ignored/untracked; `CLAUDE.md`'s reading order still uses old root paths.

## M2.4 Evidence Contract (frozen 2026-10-01; changes need explicit approval)

### Evidence vocabulary
- **CODE** — proven by source / static inspection.
- **RUNTIME** — proven by execution on a physical host. (The 2026-09-30 report's "MEASURED" = RUNTIME.)
- **CI** — proven by a GitHub Actions runner. CI is never RUNTIME and never satisfies a gate that requires RUNTIME.
- **BLOCKED** — cannot be tested yet (external dependency, missing host, or missing workflow).
- **PASS** — all acceptance criteria of the gate are met, with the evidence type the gate requires.
- **FAIL** — acceptance criteria not met.

### Gates and current status
| Gate | Acceptance | Status |
|---|---|---|
| G0 Baseline integrity | Linux Base fingerprint unchanged; protected files (`security.py`, `lifecycle.py`, `dependency_validator.py`, `web-app/`) diff-empty | PASS (RUNTIME, Linux) |
| G1-CI Windows host capability | Windows backend runs provision → prepare → blink + DHT compile → merge on a native Windows x64 GitHub runner; artifacts per the schema below | BLOCKED (CI workflow not written) |
| G1-FINAL Windows host capability | Same flow on the physical target Windows host | BLOCKED (no physical Windows host) |
| G2 ExecutionBackend | Linux backend PASS (RUNTIME). Windows backend: CI runtime PASS required, target-host runtime BLOCKED until G1-FINAL. CODE evidence: `environment.py` has no direct POSIX primitives (`unshare`, `mount`, `killpg`, `SIGKILL`, `subprocess`) — they live only in `execution.py` backends | Linux PASS (RUNTIME + CODE); Windows CI BLOCKED; Windows target-host BLOCKED |
| G3 Windows Personal E2E — **FINAL RELEASE GATE** | Real physical Windows target host + public staging Web App: pair → prepare READY → blink + DHT build → download `firmware.bin` / `wokwi-firmware.bin`; Base manifest unchanged; no `Downloading`/`Installing` in compile logs; dependency timeout kills the whole process tree. **A GitHub CI runner does NOT satisfy G3.** | BLOCKED |
| G4 Linux regression | Existing local RUNTIME evidence **plus** an automated Linux CI regression run (reproducibility). Both required for PASS | Local RUNTIME PASS; Linux CI BLOCKED (workflow not written) → G4 not final |
| G5 Cross-host semantic integrity | See below; **not** fingerprint equality | Linux half RUNTIME; Windows half BLOCKED |

**G5 semantic integrity.** MUST match between Linux and Windows: board target (`esp32dev`), framework (Arduino), package versions,
toolchain version, merge offsets (bootloader 0x1000, partitions 0x8000, firmware 0x10000; 0x0–0xFFF = 0xFF), artifact structure
(`firmware.bin`, `wokwi-firmware.bin`, ELF present, merged image layout). MAY differ: absolute paths, host OS, OS-specific binaries
(`windows_amd64` vs `linux_x86_64` toolchain), base OS metadata, and the Base listing fingerprint. Linux and Windows fingerprints
(`stat`-based vs path+size) are never compared with each other.

### CI artifact schema (Windows run, folder `m24/`)
| File | Requirement |
|---|---|
| `run-metadata.json` | `commit_sha`, `runner_os`, `runner_arch`, `python_version`, `platformio_version`, `board`, `framework`, `timestamp` |
| `gate-result.json` | per gate/criterion: `status` (PASS/FAIL/BLOCKED) **and** the list of `m24/` artifact paths that prove it. A status with no evidence path is invalid; bare `passed: true` is not accepted |
| `provisioning-run-1.log`, `provisioning-run-2.log` | full output of provision run 1 and run 2 |
| `provisioning-fingerprint-before.json`, `provisioning-fingerprint-after.json` | Base fingerprint after run 1 (valid) and after run 2; must be equal |
| `build-blink.log`, `build-dht.log` | full compile logs |
| `firmware.bin`, `firmware.elf`, `wokwi-firmware.bin`, `sha256.txt` | build outputs of the DHT build and the SHA-256 of every file in `m24/` |

### Rules and limitations
- **Provisioning idempotency** is proven inside one CI job: provision 1 → validate → provision 2 → no reinstall, no Base mutation
  (fingerprints equal). GitHub runners are ephemeral; persistence across CI runs is not testable and not claimed.
- **Windows isolation:** the Windows backend uses detection / fail-closed (Base manifest checked before/after; a changed Base fails
  the operation and marks the environment not ready; unsupported host or non-`windows_amd64` Base is refused). This is **not**
  Linux-equivalent kernel enforcement: Base writes and network use are detected, not prevented; network calls that leave no marker
  are not detected; `taskkill /T /F` does not cover processes re-parented out of the tree. Hub mode on Windows is out of scope.

## VERIFIED
- **M2.1.2 — RUNTIME:** dependency preparation (network ON) + offline compile (network OFF), timeout kill path, Base read-only +
  manifest checks. `Eksperiment/validation/m2.1.2-validation-2026-09-27.md`.
- **M2.2 — RUNTIME:** verified library catalog, `DHT.h → adafruit/DHT sensor library@1.4.4`; unverified headers get no Add button;
  `HTTPClient.h` stays core (automated + manual browser validation, 2026-09-28).
- **M2.3 — RUNTIME** (details and build ids in the M2.3 report):
  - G1 Personal default binds `127.0.0.1` only; non-loopback clients get 403 even if bound to `0.0.0.0` by hand.
  - G2 Hub is explicit opt-in (`COMPILERIO_MODE=hub`), binds `0.0.0.0`, refuses to start without an explicit non-loopback,
    non-wildcard origin allowlist.
  - G5 global waiting limit (`COMPILERIO_MAX_QUEUED_BUILDS`, default 3): race-safe admission, excess → 429, no record/dir created.
  - G6 `/environment/prepare` serialized with builds on the existing `build_lock` (FIFO).
  - G3 multi-client one-time pairing with distinct sessions; used codes rejected; one valid Hub code at a time; live 300 s expiry
    produced exactly one replacement.
  - G4 build ownership: other sessions get the same 404 as an unknown build id for status/log/firmware.
  - Hub `/environment/prepare` host-only (loopback source), 403 for remote clients before `build_lock`; not spoofable via
    forwarded headers with the launcher.
  - G7 real Web App ↔ Hub agent: host + two remote clients paired, built, polled and downloaded firmware; Personal localhost flow
    and manual agent-URL override still work.
- **Base Environment integrity — RUNTIME:** fingerprint `81655045…582c` unchanged through every M2.1.2/M2.2/M2.3 run.

## OPEN
- **Hub security limits (by design for M2.3, trusted LAN only):** plain HTTP (no TLS), tokens never expire until restart, no
  pairing rate limit, "host" = any local process on the Hub machine, manual `uvicorn` with trusted forwarded headers bypasses the
  loopback checks (launcher is safe). `/environment/status` is unauthenticated and shows the Base path.
- **Shared queue/retention:** one session can fill the global waiting limit; one session's builds can evict another's.
- **Per-request blocking:** each `POST /build` runs the synchronous Base-manifest check in the event loop (several seconds);
  bursts delay all requests. Queue rejections are evaluated after this check.
- **Web App:** CSP `connect-src` includes `http://*:8765` (any host, http, port 8765 only); port 8765 assumed by `api.js` and CSP;
  `#agentUrl` is `readonly`, so manual override is not user-typable; unused `127.0.0.1` defaults remain in `pairing.js`/`state.js`.
- **UX (pre-existing, unfixed):** reload needed after pairing and after prepare; editor usable during "Preparing Environment...";
  spacing/connection-state polish. In Hub mode the host operator must use `http://localhost:3000` to prepare.
- **Library catalog:** only `DHT.h` is verified. The other 19 headers from the removed guessed map are not in the catalog
  (`HTTPClient.h` is now classified as core); each needs Gate-1-style verification before being added.
- Version ranges (`^`, `~`) rejected by the validator — no policy decision. Dependency cache (PRD §11) not implemented.
- `logger.js` double-init unchecked. Unix-socket reachability from the compile namespace not probed.
- **Not implemented (deferred):** mDNS/discovery, tunnelling, TLS, mobile execution, UI redesign, parallel workers, per-client
  retention, persistent accounts/roles, Internet exposure.

## BLOCKERS
- **M2.4:** no Windows CI workflow yet (G1-CI, Windows G2, G4 Linux CI) and no physical Windows host (G1-FINAL, G3, Windows G5).
- Committing M2.4 changes requires explicit user approval.

## ACTIVE FILES (M2.3, committed; M2.4 files listed in Snapshot)
- `local-agent/app/config.py` — mode, port, `max_queued_builds`, Hub startup guard, `is_loopback_host`.
- `local-agent/app/__main__.py` (new) — launcher; bind from mode; `proxy_headers=False`.
- `local-agent/app/main.py` — Personal loopback middleware, prepare under `build_lock` + Hub host-only check, queue admission 429,
  `BuildRecord.session_id`, ownership in `get_build`, Hub code-expiry task.
- `local-agent/app/security.py` — `token → session_id`, locked one-time codes, Hub rotation.
- `web-app/api.js` (derived agent URL), `web-app/index.html` (CSP).
- Unchanged: `environment.py`, `lifecycle.py`, `dependency_validator.py`, `library.js`, `library-catalog.js`, `build.js`.

## LATEST EVIDENCE
- `Eksperiment/validation/m2.3-validation-2026-09-30.md` (all M2.3 gates, build ids, expiry run).
- Ad-hoc Base fingerprint: `find runtime/platformio-data -exec stat -c '%n %a %s %Y' {} + | sort | sha256sum` →
  `81655045e90ad7155aa3ae1d2f178229306cee719db8d92e3f813dd7494a582c`.

## NEXT GATE (exactly one)
**M2.4 G1-CI:** after approval of the Evidence Contract above, add a Windows x64 GitHub Actions workflow that produces the `m24/`
artifact set (provision twice, blink + DHT build) plus a Linux regression job for G4. Then G2 Windows CI half and G5 comparison.
G1-FINAL and G3 follow on the physical Windows target host with the public staging Web App.

## DO NOT REPEAT
- M2.1.2/M2.2 investigations (network boundary, ownerless specs, timeout kill, compile isolation, module exports, DHT E2E,
  catalog gating) — settled; see their reports.
- M2.3 gates G1–G7 and the live 300 s expiry run — settled; re-run only if `config.py`, `main.py`, `security.py`, `__main__.py`,
  `api.js` or the CSP change.
- A build submitted while the environment is `PREPARING` gets 409 (pre-existing readiness check) — expected, not a queue bug.
- Test hygiene: headless Chrome caches ES modules (use a fresh `--user-data-dir`); the Web App needs a reload after pair and
  after prepare; `pkill -f`/`pgrep -f` can match the calling shell (kill by port with `fuser -k <port>/tcp` or by PID file);
  a harness wait on the text "Error" matches expected "TypeError: Failed to fetch" CSP lines.
- Remote vs host on one machine: requests to the LAN IP (`192.168.1.74`) are non-loopback; requests to `127.0.0.1` are the host.
