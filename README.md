# CompilerIO

Compile ESP32 Arduino code from a browser Web App on your own machine and get a
`wokwi-firmware.bin` ready to upload manually to [Wokwi](https://wokwi.com).

A Python/FastAPI **Local Agent** receives the sketch from the Web App and builds it
with PlatformIO (`esp32dev` + Arduino framework), so no cloud compiler is needed.

## Layout

| Path | Purpose |
|------|---------|
| `web-app/` | Browser front end |
| `local-agent/` | FastAPI Local Agent + PlatformIO build orchestration |
| `docs/` | Architecture, PRD, and project state |
| `Eksperiment/` | Validation experiments and reports |

## Status

Work in progress (Milestone 2: library handling, verified library catalog,
Personal/Hub execution modes). See [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md)
for the current milestone and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design.

## Getting started

See [local-agent/README.md](local-agent/README.md) for running the Local Agent.

## License

[MIT](LICENSE)
