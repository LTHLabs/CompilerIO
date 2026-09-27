# CompilerIO — Project State (live handoff)

Update when a gate finishes: replace items, do not append history. Source code beats this file.
Labels: **CODE** = read in source, **RUNTIME** = observed in a real run. No timing/benchmark figures here (see `AGENTS.md`).

## Snapshot
- Date: 2026-09-27.
- Branch `milestone-2-library-handling`, HEAD `cf1b0d8`.
- Uncommitted changes: `local-agent/app/{dependency_validator,environment,main}.py`,
  `web-app/{build,editor,library,logger,pairing,prepare,state,wokwi}.js`, plus new `CLAUDE.md` and `docs/`.
- Active milestone: **M2.1.2 Dependency Handling**.

## VERIFIED
- **Gate 1 — RUNTIME:** owner-qualified DHT via agent API. Libdeps populated, offline compile succeeds, firmware artifacts exist,
  Base fingerprint unchanged, no orphans.
- **Gate 2 — RUNTIME (outcome level):** dependency timeout path fires; log contains `TIMEOUT (process group killed)`; no orphans;
  Base fingerprint unchanged.
- **Gate 3 — RUNTIME:** compile-namespace network probe fails (`Network is unreachable`, no DNS, only `lo`); host unaffected.
- **Gate 4 — RUNTIME:** real Web App → Agent → DHT end-to-end build via headless Chrome. Build succeeded; UI showed
  "Build Successful". Details in "Latest evidence".
- **Web App module loading — RUNTIME:** with the missing named exports added, module graph loads without link errors.
- **DHT mapping — RUNTIME:** UI's Add button carries `data-platformio="adafruit/DHT sensor library@1.4.4"`.
- **BuildRequest `lib_deps` = `string[]` — RUNTIME:** captured `/build` payload had a plain string array; agent returned 200.
- **Base Environment integrity — RUNTIME:** ad-hoc fingerprint identical before and after every gate.
- **Project-scoped dependency storage — RUNTIME:** installs land in `.pio/libdeps/esp32dev/`; no DHT/Unified Sensor paths exist under
  `runtime/platformio-data/` or `runtime/agent-state/` (outside board `variants`).
- **Firmware generation — RUNTIME:** both `firmware.bin` and `wokwi-firmware.bin` produced by Gate 1 and Gate 4.

## OPEN
- **M2.1.2 validation report** at `Eksperiment/validation/m2.1.2-validation-2026-09-27.md` — written; PASS verdict.
- **Final diff audit** of the M2.1.2 change set — done; INTENDED only.
- **Commit** of the M2.1.2 work — staged; awaiting user go-ahead.
- **Web App post-pair/post-prepare state refresh** — after `POST /session/pair` and after prepare completes READY, the app does not
  re-run `checkAgent`, so the state never transitions on its own. Gate 4 worked around this with two `Page.reload` calls (see Do Not Repeat).
- **Verification of other `EXTERNAL_LIBRARY_MAP` entries** — all remain ownerless (unverified) and will now be rejected by the validator.
- **Timeout path performance / slow cleanup** — CODE only; the cause of the extra elapsed time before returning is unmeasured.
- **Version ranges (`^`, `~`)** — rejected by the validator; no policy decision yet.
- `logger.js` registers a `DOMContentLoaded` init and `app.js` also calls `logger.init()`; double-init effect unchecked.
- **Unix-socket reachability** from the compile namespace not probed.

## BLOCKERS
- None known for the next gate.

## ACTIVE FILES
- `local-agent/app/environment.py` — dependency preparation without `--net`, reads the ini.
- `local-agent/app/dependency_validator.py` — owner-qualified Registry specs required.
- `local-agent/app/main.py` — `lib_deps` flow.
- `web-app/library.js` — DHT mapping owner-qualified.
- `web-app/build.js` — payload conversion `object[] → string[]`.
- `web-app/{editor,logger,pairing,prepare,wokwi,state}.js` — export-only edits so the module graph resolves.
- New docs: `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/PROJECT_STATE.md`.

## LATEST EVIDENCE
- Gate 4 build id `bf90f56cf659425c93488e9c80209599` (project dir may be evicted on restart).
  Log lines: `Library Manager: Installing adafruit/DHT sensor library @ 1.4.4` → installed → `Installing Adafruit Unified Sensor` → installed.
  `.pio/libdeps/esp32dev/`: `DHT sensor library/`, `Adafruit Unified Sensor/`, `integrity.dat`. Both firmware bins produced.
- Ad-hoc Base fingerprint reference across all gates:
  `find runtime/platformio-data -exec stat -c '%n %a %s %Y' {} + | sort | sha256sum` → `81655045e90ad7155aa3ae1d2f178229306cee719db8d92e3f813dd7494a582c`.
- Older reports (unrelated): `Eksperiment/validation/validation-track-2026-09-10.md`, `lifecycle-test-2026-09-11.md`.

## NEXT GATE (exactly one)
**M2.1.2 validation report + final audit and commit.** Write the M2.1.2 report to `Eksperiment/validation/`
summarizing Gates 1–4, the code changes, and their evidence. Do a final diff audit against HEAD (`cf1b0d8`).
Then, on user go-ahead, commit the Python and Web App changes together with the docs.

## DO NOT REPEAT
- `--net` on the dependency-preparation `unshare` — settled: dependency phase network ON, compile OFF.
- PlatformIO ownerless-spec behavior — settled: `pkg install -e` skips them; require `owner/name@version`.
- Timeout mechanism (kill path) — settled at the outcome level: process group killed, no orphans, log line present.
- Compile network-isolation probe — settled: namespace has only `lo`, no DNS, no outbound.
- Web App module-export investigation — settled: seven objects + `AppState` now exported.
- DHT E2E proof — settled by Gate 4; do not re-run to prove the DHT happy path.
- Headless Chrome caches ES modules: use a fresh `--user-data-dir` or disable cache.
- Web App does not refresh state after pair or prepare: reload the page between those steps until this UX bug is fixed.
- `pkill -f` / `pgrep -f` can match the current shell's own cmdline (exit 144); track PIDs in files or use psutil filters, not bracket-tricks.
