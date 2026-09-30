# CompilerIO — Project State (live handoff)

Update when a gate finishes: replace items, do not append history. Source code beats this file.
Labels: **CODE** = read in source, **RUNTIME** = observed in a real run. No timing/benchmark figures here (see `AGENTS.md`).

## Snapshot
- Date: 2026-09-30. Branch `milestone-2-library-handling`, HEAD `f45ad65`.
- Commits: `573db35` M2.1.2 → `7cd3cc5` M2.2 (DHT catalog slice) → `f45ad65` housekeeping (moved `AGENTS.md` and the PRD into
  `docs/`, removed root `CLAUDE.md`/`AGENTS.md` and two `Eksperiment/profiling` reports, `.gitignore` now ignores `CLAUDE.md`,
  `AGENTS.md`, `.claude`, `.vscode/`). The previous snapshot said HEAD `573db35` because it was written before, and committed inside,
  `7cd3cc5`.
- `CLAUDE.md` (root) and `docs/AGENTS.md` exist but are ignored/untracked; `CLAUDE.md`'s reading order still points to the old root
  paths of `AGENTS.md` and the PRD (now `docs/AGENTS.md`, `docs/Product Requirements Document (PRD).md`).
- Uncommitted: **M2.3 Execution Mode Foundation** — `local-agent/app/{config,main,security}.py`, new `local-agent/app/__main__.py`,
  `web-app/{api.js,index.html}`, docs (`local-agent/README.md`, `docs/ARCHITECTURE.md`, this file) and
  `Eksperiment/validation/m2.3-validation-2026-09-30.md`. Awaiting commit approval.
- Active milestone: M2.3 — all gates passed (see VERIFIED). Report: `Eksperiment/validation/m2.3-validation-2026-09-30.md`.

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
- None for committing M2.3; commit requires explicit user approval.

## ACTIVE FILES (M2.3)
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
**Commit M2.3** after explicit user approval: stage only the M2.3 files listed in ACTIVE FILES plus `local-agent/README.md`,
`docs/ARCHITECTURE.md`, `docs/PROJECT_STATE.md` and the M2.3 report. Do not include ignored or unrelated files.

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
