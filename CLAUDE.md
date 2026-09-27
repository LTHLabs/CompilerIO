# CompilerIO — Claude Code Bootstrap

CompilerIO lets a browser Web App compile ESP32 (esp32dev + Arduino) Arduino code on the user's machine through a
Python/FastAPI Local Agent and PlatformIO, producing `wokwi-firmware.bin` for manual upload to Wokwi.

## Reading order
1. `AGENTS.md` — guardrails, protected foundations, approval rules (authoritative; not repeated here)
2. `docs/PROJECT_STATE.md` — live handoff: milestone, verified / not verified, blockers, next gate
3. `docs/ARCHITECTURE.md` — stable architecture
4. `Product Requirements Document (PRD).md` — only when scope or requirements are in doubt

## Working rules
- Label every claim **CODE VERIFIED** (read in source) or **RUNTIME VERIFIED** (observed in a real run). Never assume PASS.
- Inspect before modify. Read the relevant source first; source code beats docs when they conflict.
- Do not repeat completed investigations (see "Do Not Repeat" in `docs/PROJECT_STATE.md`) unless the code or evidence changed.
- Respect plan mode and the file allow-lists given per task. High-risk files need explicit approval (see `AGENTS.md`).
- Update `docs/PROJECT_STATE.md` when a gate finishes. Keep it short; replace, do not append history.
