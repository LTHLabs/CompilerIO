# CompilerIO — Project State (live handoff)

Update when a gate finishes: replace items, do not append history. Source code beats this file.
Labels: **CODE** = read in source, **RUNTIME** = observed in a real run. No timing/benchmark figures here (see `AGENTS.md`).

## Snapshot
- Date: 2026-09-30.
- Branch `milestone-2-library-handling`. HEAD `573db35` (M2.1.2), parent `cf1b0d8` — confirmed via `git log`/`git rev-parse`.
- Uncommitted, M2.2-scoped: new `web-app/library-catalog.js`; modified `web-app/library.js`, `docs/ARCHITECTURE.md`,
  `docs/PROJECT_STATE.md`. Manual browser validation of this slice passed on 2026-09-28 (see VERIFIED).
- Uncommitted, **unrelated to M2.2** (present in the working tree, not made by this milestone, not to be touched
  or committed here): `AGENTS.md`, `CLAUDE.md`, and `Product Requirements Document (PRD).md` show as deleted from
  their tracked root paths; byte-identical copies now exist at `docs/CLAUDE.md`, `docs/AGENTS.md`, and
  `docs/Product Requirements Document (PRD).md` (the first two are invisible to `git status` because `.gitignore`
  ignores the bare names `CLAUDE.md`/`AGENTS.md` at any depth; the PRD copy shows as `??`). `.gitignore` itself is
  modified, and two `Eksperiment/profiling/*.md` files are deleted — both predate M2.2. None of this was changed by
  this task; flagged here only for accuracy of "current HEAD/commit state."
- Active milestone: **M2.2 Verified Library/Dependency Catalog** — DHT slice implemented, re-verified at runtime,
  and manually validated in a real browser. The remaining 15 previously-guessed headers are not yet in the catalog
  (see OPEN).

## VERIFIED
- **M2.1.2 Gates 1–4 — RUNTIME:** dependency preparation + offline compile, timeout kill path, compile network
  isolation, and a real Web App → Agent → DHT build. See `Eksperiment/validation/m2.1.2-validation-2026-09-27.md`.
- **M2.2 DHT catalog slice — RUNTIME:** `web-app/library-catalog.js` (`LIBRARY_CATALOG`) replaces
  `EXTERNAL_LIBRARY_MAP` as the mapping source in `library.js`. Re-ran the Gate-4 method end to end (fresh Chrome
  profile, pair → prepare → detect → Add → Compile): `data-platformio="adafruit/DHT sensor library@1.4.4"`,
  `/build` payload `lib_deps:["adafruit/DHT sensor library@1.4.4"]`, agent returned 200, build `SUCCEEDED`
  ("Build Successful", firmware size 329.2 KB). See "Latest evidence" for the build id and artifact check.
- **Unverified headers no longer guess a spec — RUNTIME:** `resolveLibrary` on a header absent from the catalog
  (e.g. `Servo.h`) returns `platformioName: null` and is classified `unknown`; `renderLibraryPanel` renders no Add
  button for it, so it cannot enter `selectedLibDeps` or the `/build` payload (confirmed by reading the rendered
  branch logic and by the in-process `resolveLibrary`/`classifyHeader` checks; not re-driven through the browser
  for a non-DHT header in this run).
- **`HTTPClient.h` stays `core`, not `external` — RUNTIME (in-process check):** `classifyHeader('HTTPClient.h', 'system')`
  returns `core`; the former duplicate/dead `EXTERNAL_LIBRARY_MAP` entry for it no longer exists (removed with the
  rest of the guessed map).
- **Base Environment integrity — RUNTIME:** ad-hoc fingerprint identical before and after this run
  (`81655045…582c`, same value as every M2.1.2 gate).
- **M2.2 manual UI validation — RUNTIME (real browser, 2026-09-28):** three cases exercised by hand against the
  live Web App + Agent (not headless-driven):
  - `Servo.h` (not in catalog) → badge "⚠ Not in verified catalog", no Add button. PASS.
  - `HTTPClient.h` (core header) → listed only under "Core (Arduino ESP32)", no "External Libraries" group. PASS.
  - `DHT.h` (catalog hit) → badge "📦 DHT sensor library", Add button with spec `adafruit/DHT sensor library@1.4.4`,
    Add → Remove toggle works. PASS.
  Screenshot evidence: `Hasil-compiler-DHT.png` (held by the user, not committed to the repo by this task).

## OPEN
- **Remaining 15 headers** (`DHTesp.h`, `Adafruit_Sensor.h`, `Adafruit_BME280.h`, `Adafruit_SSD1306.h`,
  `ArduinoJson.h`, `PubSubClient.h`, `WebSocketsClient.h`, `ESPAsyncWebServer.h`, `AsyncTCP.h`, `OneWire.h`,
  `DallasTemperature.h`, `MQTT.h`, `HTTPClient.h`, `TimeLib.h`, `NTPClient.h`, `U8g2lib.h`, `TFT_eSPI.h`,
  `FastLED.h`, `Servo.h`) are **not** in `library-catalog.js`. They now render as "Not in verified catalog" with no
  Add button — a UX regression from "guessed and silently broken" to "explicitly unavailable," which is the
  intended M2.2 behavior, but means none of these headers can be built via the picker until each is verified and
  added using the same method as DHT (Gate-1-style: submit build → confirm `.pio/libdeps` → confirm compile →
  confirm Base fingerprint unchanged).
- **Web App post-pair/post-prepare state refresh** — still unfixed; this run again worked around it with two
  `Page.reload` calls (see Do Not Repeat).
- **Version ranges (`^`, `~`)** — still rejected by the validator; no policy decision.
- **Dependency cache** (PRD §11: cross-build reuse of downloaded packages) — not implemented; out of scope for
  M2.2, which only changed which specs are offered, not how/when they're installed or cached.
- `logger.js` double-init (`DOMContentLoaded` handler + explicit `app.js` call) — still unchecked.
- **Unix-socket reachability** from the compile namespace — still not probed.
- **Three UI observations from manual validation (2026-09-28), non-blocking, not fixed by M2.2:**
  1. A page refresh is still needed after pairing before the app reliably advances (same root cause as the
     "Web App post-pair/post-prepare state refresh" item above).
  2. The code editor remains interactable while the environment is "Preparing Environment..." — nothing stops a
     user from typing or clicking Compile mid-prepare.
  3. Editor spacing/padding and the initial connection-state synchronization need visual/UX polish.
  None of these are library-catalog issues; they belong to a future Web App UX pass, not M2.2.

## BLOCKERS
- None known for the next gate.

## ACTIVE FILES
- `web-app/library-catalog.js` **(new)** — `LIBRARY_CATALOG`: header → `{name, platformioName, verifiedAt, verifiedBy}`.
  DHT.h only.
- `web-app/library.js` — imports `LIBRARY_CATALOG` instead of the old hard-coded `EXTERNAL_LIBRARY_MAP`;
  `classifyHeader`/`resolveLibrary` source from it; `renderLibraryPanel` gates the Add button on a catalog hit
  (`isVerified`) so an unmapped header gets a badge only, never a selectable action. Include-detection/parsing
  logic (`detectIncludes`, `matchInclude`) untouched.
- Not touched this run: `local-agent/*`, `web-app/build.js`, `web-app/{api,app,editor,logger,pairing,prepare,state,wokwi}.js`,
  `security.py`, `lifecycle.py`, Base Environment.

## LATEST EVIDENCE
- M2.2 DHT re-verification build id `ec0dbf9022074fe88cb74f970ee01d28` (project dir may be evicted on restart).
  `.pio/libdeps/esp32dev/`: `DHT sensor library/`, `Adafruit Unified Sensor/`, `integrity.dat`. Both `firmware.bin`
  and `wokwi-firmware.bin` present under `.pio/build/esp32dev/`.
- Ad-hoc Base fingerprint reference (unchanged since M2.1.2):
  `find runtime/platformio-data -exec stat -c '%n %a %s %Y' {} + | sort | sha256sum` → `81655045e90ad7155aa3ae1d2f178229306cee719db8d92e3f813dd7494a582c`.
- M2.1.2 evidence: `Eksperiment/validation/m2.1.2-validation-2026-09-27.md`.

## NEXT GATE (exactly one)
**Verify and add one more catalog entry** using the same method as DHT (submit build with a candidate
owner-qualified spec → confirm `.pio/libdeps/esp32dev/` contents → confirm offline compile succeeds → confirm Base
fingerprint unchanged), then add it to `library-catalog.js` with `verifiedAt`/`verifiedBy`. Repeat per-header; this
is intentionally not batched into one task.

## DO NOT REPEAT
- M2.1.2 items (network boundary, ownerless-spec behavior, timeout kill path, compile network isolation, Web App
  module-export fix) — all settled; see the M2.1.2 validation report, do not re-investigate.
- DHT E2E proof — settled three times now (M2.1.2 Gate 4, M2.2 automated re-verification, M2.2 manual browser
  validation); do not re-run to prove the DHT happy path again unless `library.js`/`library-catalog.js` changes.
- Servo.h / HTTPClient.h gating (no Add button for unverified, core headers never show as external) — settled by
  manual validation; do not re-verify unless `library.js`'s classify/resolve/render logic changes.
- Headless Chrome caches ES modules: use a fresh `--user-data-dir` or disable cache.
- Web App does not refresh state after pair or prepare: reload the page between those steps until this UX bug is fixed.
- `pkill -f` / `pgrep -f` can match the current shell's own cmdline text (exit 144). Prefer killing by port
  (`fuser -k <port>/tcp`) or by tracked PID files over pattern matching against cmdline.
