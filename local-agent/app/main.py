from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .config import HUB_MODE, PERSONAL_MODE, Settings, is_loopback_host
from .dependency_validator import validate_lib_deps
from .environment import EnvironmentManager
from .execution import ExecResult
from .lifecycle import BuildJanitor
from .security import SessionManager


class PairRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128)


class BuildRequest(BaseModel):
    source_code: str = Field(min_length=1, max_length=200_000)
    board: str = "esp32dev"
    framework: str = "arduino"
    lib_deps: list[str] = Field(default_factory=list)
    project_name: str | None = None


@dataclass
class BuildRecord:
    build_id: str
    project_dir: Path
    status: str = "QUEUED"
    duration_seconds: float | None = None
    log: str = ""
    error: str | None = None
    artifacts: dict[str, Path] = field(default_factory=dict)
    # Session that created the build; internal only, never returned in responses.
    session_id: str = ""


settings = Settings.from_environment()
environment = EnvironmentManager(settings)
sessions = SessionManager(settings)
janitor = BuildJanitor(settings.projects_dir, settings.build_retention)
build_lock = asyncio.Lock()
builds: dict[str, BuildRecord] = {}

app = FastAPI(title="Local ESP32 Compiler Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["content-type", "x-local-agent-token"],
)


@app.middleware("http")
async def enforce_personal_loopback(request: Request, call_next):
    # Personal mode serves the local user only, however the server was launched
    # (e.g. a manual `uvicorn --host 0.0.0.0`): reject every non-loopback client.
    if settings.mode == PERSONAL_MODE:
        client_host = request.client.host if request.client else None
        if not is_loopback_host(client_host):
            return JSONResponse(status_code=403, content={"detail": "Personal mode accepts loopback clients only."})
    return await call_next(request)


def protected(request: Request) -> str:
    """Validate origin and token; return the caller's session_id."""
    sessions.validate_origin(request)
    return sessions.require_token(request)


async def rotate_expired_pairing_codes() -> None:
    # Hub only: keep exactly one valid pairing code available for the next client.
    while True:
        await asyncio.sleep(1)
        sessions.rotate_if_expired()


@app.on_event("startup")
async def show_pairing_code() -> None:
    print(f"Local Agent mode: {settings.mode} (launcher bind address {settings.host}:{settings.port})", flush=True)
    if settings.mode != PERSONAL_MODE:
        print(
            "WARNING: Hub mode is reachable from the network over plain HTTP. Use it on a trusted LAN only. "
            f"Allowed origins: {', '.join(sorted(settings.allowed_origins))}",
            flush=True,
        )
    sweep_failures = janitor.sweep_startup()
    if sweep_failures:
        print(f"Local Agent startup sweep could not delete {len(sweep_failures)} path(s): {sweep_failures}", flush=True)
    print(f"Local Agent pairing code (valid {settings.pairing_ttl_seconds}s): {sessions.pairing_code()}", flush=True)
    if settings.mode == HUB_MODE:
        asyncio.create_task(rotate_expired_pairing_codes())


@app.get("/environment/status")
def environment_status() -> dict[str, object]:
    return environment.status()


@app.post("/environment/prepare", dependencies=[Depends(protected)])
async def environment_prepare(request: Request) -> dict[str, object]:
    # Hub mode: only the host machine (loopback connection source) may prepare. Checked
    # before build_lock so a rejected remote request never waits on or holds the lock.
    if settings.mode == HUB_MODE and not is_loopback_host(request.client.host if request.client else None):
        raise HTTPException(status_code=403, detail="Environment preparation is host-only in Hub mode.")
    # Serialized with builds: prepare runs a validation compile and re-takes the Base
    # manifest baseline, so it must never overlap an active build.
    async with build_lock:
        status = await asyncio.to_thread(environment.prepare)
        if status["status"] == "READY":
            cleanup_failures = janitor.cleanup_validation_dirs()
            if cleanup_failures:
                print(f"Local Agent could not delete {len(cleanup_failures)} validation dir(s): {cleanup_failures}", flush=True)
    return status


@app.post("/session/pair")
def pair(request: Request, body: PairRequest) -> dict[str, str]:
    sessions.validate_origin(request)
    return {"token": sessions.pair(body.code)}


@app.get("/boards")
def list_boards() -> list[dict[str, object]]:
    return [{"id": "esp32dev", "name": "ESP32 DevKit V1", "default": True}]


@app.get("/frameworks")
def list_frameworks() -> list[dict[str, object]]:
    return [{"id": "arduino", "name": "Arduino", "default": True}]


@app.post("/build")
async def create_build(body: BuildRequest, session_id: str = Depends(protected)) -> dict[str, str]:
    if body.board != "esp32dev" or body.framework != "arduino":
        raise HTTPException(status_code=422, detail="Only esp32dev with Arduino is supported.")
    try:
        environment.assert_ready()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Admission is race-safe: there is no await between this count and the insert
    # below, so concurrent submissions are admitted one at a time by the event loop.
    queued = sum(1 for existing in builds.values() if existing.status == "QUEUED")
    if queued >= settings.max_queued_builds:
        raise HTTPException(
            status_code=429,
            detail=f"Build queue is full ({queued} waiting). Try again after a build finishes.",
        )
    build_id = uuid.uuid4().hex
    project_dir = settings.projects_dir / build_id
    record = BuildRecord(build_id=build_id, project_dir=project_dir, session_id=session_id)
    builds[build_id] = record
    asyncio.create_task(run_build(record, body.source_code, body.lib_deps))
    return {"build_id": build_id, "status": record.status}


# async def run_build(record: BuildRecord, source_code: str) -> None:
#     async with build_lock:
#         record.status = "RUNNING"
#         started = time.monotonic()
#         try:
#             write_project(record.project_dir, source_code)
#             result = await asyncio.to_thread(environment.run_platformio, record.project_dir)
#             record.log = result.stdout + result.stderr
#             (record.project_dir / "platformio.log").write_text(record.log, encoding="utf-8")
#             if result.returncode != 0:
#                 record.status = "FAILED"
#                 record.error = "PlatformIO compilation failed."
#                 return
#             artifacts = record.project_dir / ".pio" / "build" / "esp32dev"
#             record.artifacts["firmware.bin"] = artifacts / "firmware.bin"
#             record.artifacts["firmware.elf"] = artifacts / "firmware.elf"
#             merged = artifacts / "wokwi-firmware.bin"
#             merge_result = await asyncio.to_thread(merge_firmware, record.project_dir, merged)
#             record.log += "\n" + merge_result.stdout + merge_result.stderr
#             if merge_result.returncode != 0:
#                 record.status = "FAILED"
#                 record.error = "Firmware merge_bin failed."
#                 return
#             record.artifacts["wokwi-firmware.bin"] = merged
#             record.status = "SUCCEEDED"
#         except Exception as exc:
#             record.status = "FAILED"
#             record.error = str(exc)
#         finally:
#             record.duration_seconds = round(time.monotonic() - started, 3)

def _timing_value(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "unavailable"


async def run_build(record: BuildRecord, source_code: str, lib_deps: list[str]) -> None:
    async with build_lock:
        record.status = "RUNNING"
        started = time.monotonic()
        setup_seconds: float | None = None
        dependency_prepare_seconds: float | None = None
        platformio_seconds: float | None = None
        merge_seconds: float | None = None

        try:
            is_valid, error = validate_lib_deps(lib_deps)
            if not is_valid:
                record.status = "FAILED"
                record.error = f"Invalid lib_deps: {error}"
                record.log += f"\n[CompilerIO] Dependency validation failed: {error}"
                return

            t = time.monotonic()
            write_project(record.project_dir, source_code, lib_deps)
            setup_seconds = time.monotonic() - t

            t = time.monotonic()
            dep_result = await asyncio.to_thread(
                environment.prepare_dependencies,
                record.project_dir,
                settings.dependency_prepare_timeout,
            )
            dependency_prepare_seconds = time.monotonic() - t

            record.log += (
                f"\n[CompilerIO] Dependency preparation\n"
                f"{dep_result.stdout}{dep_result.stderr}"
            )

            if dep_result.returncode != 0:
                record.status = "FAILED"
                if dep_result.timed_out:
                    record.error = f"Dependency preparation timed out after {settings.dependency_prepare_timeout}s"
                    record.log += f"\n[CompilerIO] Dependency preparation TIMEOUT (process group killed)"
                else:
                    record.error = "Dependency preparation failed."
                return

            t = time.monotonic()
            result = await asyncio.to_thread(
                environment.run_platformio,
                record.project_dir
            )
            platformio_seconds = time.monotonic() - t

            record.log += (
                f"\n[CompilerIO] Compilation\n"
                f"{result.stdout}{result.stderr}"
            )
            (record.project_dir / "platformio.log").write_text(
                record.log,
                encoding="utf-8",
            )

            if result.returncode != 0:
                record.status = "FAILED"
                record.error = "PlatformIO compilation failed."
                return

            artifacts = (
                record.project_dir
                / ".pio"
                / "build"
                / "esp32dev"
            )

            record.artifacts["firmware.bin"] = artifacts / "firmware.bin"
            record.artifacts["firmware.elf"] = artifacts / "firmware.elf"

            merged = artifacts / "wokwi-firmware.bin"

            t = time.monotonic()
            merge_result = await asyncio.to_thread(
                merge_firmware,
                record.project_dir,
                merged
            )
            merge_seconds = time.monotonic() - t

            record.log += (
                f"\n[CompilerIO] Firmware merge\n"
                f"{merge_result.stdout}{merge_result.stderr}"
            )

            if merge_result.returncode != 0:
                record.status = "FAILED"
                record.error = "Firmware merge_bin failed."
                return

            record.artifacts["wokwi-firmware.bin"] = merged
            record.status = "SUCCEEDED"

        except Exception as exc:
            record.status = "FAILED"
            record.error = str(exc)

        finally:
            total_seconds = time.monotonic() - started
            record.duration_seconds = round(total_seconds, 3)
            record.log += (
                f"\n\n[CompilerIO timing]\n"
                f"project_setup_seconds={_timing_value(setup_seconds)}\n"
                f"dependency_prepare_seconds={_timing_value(dependency_prepare_seconds)}\n"
                f"platformio_seconds={_timing_value(platformio_seconds)}\n"
                f"merge_seconds={_timing_value(merge_seconds)}\n"
                f"total_seconds={_timing_value(total_seconds)}\n"
            )

            janitor.enforce(builds)

def write_project(project_dir: Path, source_code: str, lib_deps: list[str]) -> None:
    (project_dir / "src").mkdir(parents=True, exist_ok=False)
    ini_content = "[env:esp32dev]\nplatform = espressif32\nboard = esp32dev\nframework = arduino\n"
    if lib_deps:
        ini_content += "lib_deps =\n"
        for dep in lib_deps:
            ini_content += f"    {dep}\n"
    (project_dir / "platformio.ini").write_text(ini_content, encoding="utf-8")
    (project_dir / "src" / "main.cpp").write_text(source_code, encoding="utf-8")


def merge_firmware(project_dir: Path, output: Path) -> ExecResult:
    build_dir = project_dir / ".pio" / "build" / "esp32dev"
    esptool = settings.base_environment / "packages" / "tool-esptoolpy" / "esptool.py"
    return environment.run_readonly_command(
        [
            str(settings.python_executable), str(esptool), "--chip", "esp32", "merge_bin", "-o", str(output),
            "--flash_mode", "dio", "--flash_freq", "40m", "--flash_size", "4MB",
            "0x1000", str(build_dir / "bootloader.bin"),
            "0x8000", str(build_dir / "partitions.bin"),
            "0x10000", str(build_dir / "firmware.bin"),
        ],
        cwd=project_dir,
    )


def get_build(build_id: str, session_id: str) -> BuildRecord:
    # Unknown builds and builds owned by another session get the identical 404,
    # so a caller cannot learn whether a foreign build_id exists.
    record = builds.get(build_id)
    if record is None or not secrets.compare_digest(record.session_id, session_id):
        raise HTTPException(status_code=404, detail="Build not found.")
    return record


@app.get("/build/{build_id}/status")
def build_status(build_id: str, session_id: str = Depends(protected)) -> dict[str, object]:
    record = get_build(build_id, session_id)
    return {"build_id": record.build_id, "status": record.status, "duration_seconds": record.duration_seconds, "error": record.error}


@app.get("/build/{build_id}/log", response_class=PlainTextResponse)
def build_log(build_id: str, session_id: str = Depends(protected)) -> str:
    return get_build(build_id, session_id).log


@app.get("/build/{build_id}/firmware/{artifact_name}")
def download_firmware(build_id: str, artifact_name: str, session_id: str = Depends(protected)) -> FileResponse:
    record = get_build(build_id, session_id)
    artifact = record.artifacts.get(artifact_name)
    if artifact is None or not artifact.is_file():
        raise HTTPException(status_code=404, detail="Firmware artifact is unavailable.")
    return FileResponse(artifact, filename=artifact.name, media_type="application/octet-stream")
