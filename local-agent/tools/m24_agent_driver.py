#!/usr/bin/env python3
"""M2.4 agent driver: exercises the existing Local Agent over HTTP and collects evidence into an `m24/` directory.

Subcommands
  run                 start the agent, pair -> prepare -> blink build -> DHT build -> collect logs/artifacts, stop the agent
  copy-provisioning   copy runtime/windows-base-provision.json (fixed path written by provision-windows-base.ps1)
                      to a caller-selected file (used for provisioning-fingerprint-before/after.json)

`run` writes into --out (contract files at the top level, supplementary evidence under aux/):
  run-metadata.json, build-blink.log, build-dht.log, firmware.bin, firmware.elf, wokwi-firmware.bin  (DHT build only)
  aux/driver-result.json, aux/agent-stdout.log, aux/agent-stderr.log, aux/environment-*.json, aux/build-*-status.json,
  aux/backend-inference.json, aux/merge-sources.json, aux/base-fingerprint.json, aux/protected-files-check.json
It never writes gate-result.json or sha256.txt (see m24_gate_evaluator.py) and never fabricates a missing artifact.

Exit codes: 0 all steps ok, 1 a step failed or timed out (evidence collected so far is kept), 2 usage / preflight error,
3 copy-provisioning source missing (BLOCKED).

Standard library only. Does not modify the Local Agent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FROZEN_DHT_SPEC = "adafruit/DHT sensor library@1.4.4"
BASELINE_COMMIT = "ccbcc91"
PROTECTED_PATHS = (
    "local-agent/app/security.py",
    "local-agent/app/lifecycle.py",
    "local-agent/app/dependency_validator.py",
    "web-app/",
)
PROVISION_EVIDENCE = Path("runtime") / "windows-base-provision.json"
PAIRING_RE = re.compile(r"Local Agent pairing code \(valid \d+s\): (\S+)")
TERMINAL_BUILD = ("SUCCEEDED", "FAILED")
DHT_ARTIFACTS = ("firmware.bin", "firmware.elf", "wokwi-firmware.bin")

BLINK_SOURCE = (
    "#include <Arduino.h>\n"
    "void setup() { pinMode(2, OUTPUT); }\n"
    "void loop() { digitalWrite(2, HIGH); delay(500); digitalWrite(2, LOW); delay(500); }\n"
)
DHT_SOURCE = (
    "#include <Arduino.h>\n#include <DHT.h>\n#define DHTPIN 4\n#define DHTTYPE DHT22\n"
    "DHT dht(DHTPIN, DHTTYPE);\n"
    "void setup() { Serial.begin(115200); dht.begin(); }\n"
    "void loop() { delay(2000); float h = dht.readHumidity(); float t = dht.readTemperature();\n"
    "  if (isnan(h) || isnan(t)) { Serial.println(\"read failed\"); return; }\n"
    "  Serial.print(h); Serial.print(' '); Serial.println(t); }\n"
)


class StepFailure(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_workspace() -> Path:
    return Path(__file__).resolve().parents[2]


def venv_python(workspace: Path) -> Path:
    sub = Path("Scripts") / "python.exe" if os.name == "nt" else Path("bin") / "python"
    return workspace / "local-agent" / "venv" / sub


def http(method: str, url: str, *, headers: dict[str, str] | None = None, body: object | None = None, timeout: float = 30):
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def port_in_use(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


class AgentProcess:
    """The Local Agent started through its supported entry point (`python -m app`, Personal mode)."""

    def __init__(self, workspace: Path, port: int, aux: Path, python: Path) -> None:
        self.workspace, self.port, self.aux, self.python = workspace, port, aux, python
        self.proc: subprocess.Popen | None = None
        self.pairing_code: str | None = None
        self._threads: list[threading.Thread] = []
        self.command = [str(python), "-m", "app"]
        self.shutdown = "not-started"
        self.exit_code: int | None = None

    def start(self) -> None:
        env = os.environ.copy()
        env.update(
            PYTHONPATH=str(self.workspace / "local-agent"),
            COMPILERIO_PORT=str(self.port),
            COMPILERIO_WORKSPACE_ROOT=str(self.workspace),
            COMPILERIO_MODE="personal",
            PYTHONUNBUFFERED="1",
        )
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.proc = subprocess.Popen(
            self.command, cwd=self.workspace, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags
        )
        for stream, name in ((self.proc.stdout, "agent-stdout.log"), (self.proc.stderr, "agent-stderr.log")):
            thread = threading.Thread(target=self._pump, args=(stream, self.aux / name, name == "agent-stdout.log"), daemon=True)
            thread.start()
            self._threads.append(thread)

    def _pump(self, stream, path: Path, parse_pairing: bool) -> None:
        with path.open("wb") as sink:
            for raw in iter(stream.readline, b""):
                sink.write(raw)
                sink.flush()
                if parse_pairing and self.pairing_code is None:
                    match = PAIRING_RE.search(raw.decode("utf-8", errors="replace"))
                    if match:
                        self.pairing_code = match.group(1)

    def wait_pairing_code(self, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.pairing_code:
                return self.pairing_code
            if self.proc is not None and self.proc.poll() is not None:
                raise StepFailure(f"agent exited during startup (code {self.proc.returncode}); see aux/agent-stderr.log")
            time.sleep(0.2)
        raise StepFailure("pairing code not found on agent stdout before timeout")

    def stop(self) -> None:
        proc = self.proc
        if proc is None:
            return
        if proc.poll() is not None:
            self.shutdown = "already-exited"
        else:
            try:
                if os.name == "nt":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.terminate()
                proc.wait(timeout=20)
                self.shutdown = "terminate"
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
                self.shutdown = "kill"
        self.exit_code = proc.returncode
        for thread in self._threads:
            thread.join(timeout=5)

    def clean_exit(self) -> bool:
        """Graceful stop and an exit status that only means 'stopped by our signal' (uvicorn re-raises it)."""
        if self.shutdown != "terminate":
            return False
        accepted = {0, -signal.SIGTERM} if os.name != "nt" else {0, 3221225786}  # 0xC000013A = CTRL_BREAK
        return self.exit_code in accepted


class Driver:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.workspace = Path(args.workspace_root).resolve()
        self.out = Path(args.out).resolve()
        self.aux = self.out / "aux"
        self.base = f"http://127.0.0.1:{args.port}"
        self.origin = args.origin
        self.token: str | None = None
        self.steps: list[dict[str, str]] = []
        self.result: dict[str, object] = {
            "schema": "compilerio.m24.driver-result/1",
            "agent": {}, "pairing": {"paired": False}, "environment": {}, "builds": {},
        }
        self.python = Path(args.python) if args.python else venv_python(self.workspace)
        self.agent = AgentProcess(self.workspace, args.port, self.aux, self.python)

    # ---- bookkeeping -------------------------------------------------------------------
    def step(self, name: str, status: str, detail: str = "") -> None:
        self.steps.append({"name": name, "status": status, "detail": detail})
        print(f"[m24-driver] {name}: {status}{(' - ' + detail) if detail else ''}", flush=True)

    def headers(self, auth: bool = True) -> dict[str, str]:
        hdrs = {"Origin": self.origin}
        if auth and self.token:
            hdrs["x-local-agent-token"] = self.token
        return hdrs

    def get_json(self, path: str, auth: bool = False):
        status, body = http("GET", self.base + path, headers=self.headers(auth))
        if status != 200:
            raise StepFailure(f"GET {path} -> HTTP {status}")
        return json.loads(body)

    # ---- evidence helpers --------------------------------------------------------------
    def base_fingerprint(self) -> dict[str, object]:
        """Linux Base fingerprint with the frozen G0 command (path, mode, size, mtime). Linux only."""
        if not sys.platform.startswith("linux"):
            return {"available": False, "reason": f"Linux-only baseline fingerprint; host is {sys.platform}"}
        needed = [tool for tool in ("find", "stat", "sort", "sha256sum") if shutil.which(tool) is None]
        if needed or not (self.workspace / "runtime" / "platformio-data").is_dir():
            return {"available": False, "reason": f"missing tools {needed} or runtime/platformio-data"}
        command = "find runtime/platformio-data -exec stat -c '%n %a %s %Y' {} + | sort | sha256sum"
        done = subprocess.run(["sh", "-c", command], cwd=self.workspace, capture_output=True, text=True, check=False)
        if done.returncode != 0 or not done.stdout.strip():
            return {"available": False, "reason": f"fingerprint command failed: {done.stderr.strip()[:200]}"}
        return {"available": True, "algorithm": command, "sha256": done.stdout.split()[0]}

    def git(self, *git_args: str) -> subprocess.CompletedProcess | None:
        if shutil.which("git") is None:
            return None
        return subprocess.run(["git", "-C", str(self.workspace), *git_args], capture_output=True, text=True, check=False)

    def write_run_metadata(self, board: str, framework: str) -> None:
        env = os.environ
        sha, sha_source, dirty = env.get("GITHUB_SHA"), "GITHUB_SHA", None
        head = self.git("rev-parse", "HEAD")
        if sha is None:
            sha, sha_source = (head.stdout.strip(), "git rev-parse HEAD") if head and head.returncode == 0 else (None, None)
        status = self.git("status", "--porcelain")
        if status is not None and status.returncode == 0:
            dirty = bool(status.stdout.strip())
        py = subprocess.run(
            [str(self.python), "-c", "import platform;print(platform.python_version())"], capture_output=True, text=True, check=False
        )
        pio = subprocess.run(
            [str(self.python), "-c", "import platformio;print(platformio.__version__)"], capture_output=True, text=True, check=False
        )
        meta = {
            "schema": "compilerio.m24.run-metadata/1",
            "commit_sha": sha,
            "commit_sha_source": sha_source,
            "worktree_dirty": dirty,
            "runner_os": env.get("RUNNER_OS"),
            "runner_arch": env.get("RUNNER_ARCH"),
            "ci": env.get("GITHUB_ACTIONS") == "true",
            "github_run_id": env.get("GITHUB_RUN_ID"),
            "github_workflow": env.get("GITHUB_WORKFLOW"),
            "host_os": platform.system(),
            "host_arch": platform.machine(),
            "host_platform": sys.platform,
            "python_version": py.stdout.strip() or None,
            "platformio_version": pio.stdout.strip() or None,
            "board": board,
            "framework": framework,
            "timestamp": utc_now(),
        }
        meta["unavailable"] = sorted(key for key, value in meta.items() if value is None)
        write_json(self.out / "run-metadata.json", meta)

    def infer_backend(self) -> dict[str, object]:
        """Backend evidence from the filesystem only (the API does not report the backend)."""
        core = self.workspace / "runtime" / "agent-state" / "platformio-core"  # mirrors config.py agent_core_dir
        isjunction = getattr(os.path, "isjunction", None)  # Python 3.12+
        entries = []
        for rel in sorted([p for p in (core / "packages").glob("*")] + [core / "platforms" / "espressif32"]):
            if not rel.exists() and not rel.is_symlink():
                continue
            junction = bool(isjunction and isjunction(rel))
            kind = "junction" if junction else "symlink" if rel.is_symlink() else "dir" if rel.is_dir() else "file"
            empty = kind == "dir" and not any(rel.iterdir())
            entries.append({"path": rel.relative_to(core).as_posix(), "kind": kind, "empty_dir": empty})
        kinds = {e["kind"] for e in entries}
        if entries and kinds == {"junction"}:
            inferred = "WindowsBackend"
        elif entries and all(e["kind"] == "dir" and e["empty_dir"] for e in entries):
            inferred = "LinuxBackend"
        else:
            inferred = "undetermined"
        expected = "LinuxBackend" if sys.platform.startswith("linux") else "WindowsBackend" if sys.platform == "win32" else "UnsupportedHostBackend"
        return {
            "basis": "agent core dir entries: junctions => WindowsBackend (_link_base_packages); empty mount-target dirs => "
                     "LinuxBackend (_prepare_mount_targets). Inference only: the API does not report the active backend.",
            "host_platform": sys.platform,
            "expected_backend": expected,
            "inferred_backend": inferred,
            "entries": entries,
        }

    def collect_merge_sources(self, build_id: str) -> dict[str, object]:
        build_dir = self.workspace / "runtime" / "projects" / build_id / ".pio" / "build" / "esp32dev"
        files = {}
        for name in ("bootloader.bin", "partitions.bin", "firmware.bin"):
            path = build_dir / name
            files[name] = {"size": path.stat().st_size, "sha256": sha256_file(path)} if path.is_file() else None
        return {"build_id": build_id, "files": files, "note": "hashes of merge_bin inputs read from the agent project dir"}

    def protected_check(self) -> dict[str, object]:
        resolved = self.git("rev-parse", "--verify", f"{BASELINE_COMMIT}^{{commit}}")
        if resolved is None or resolved.returncode != 0:
            return {"available": False, "baseline": BASELINE_COMMIT, "reason": "baseline commit not resolvable in this checkout"}
        diff = self.git("diff", "--stat", BASELINE_COMMIT, "--", *PROTECTED_PATHS)
        if diff is None or diff.returncode != 0:
            return {"available": False, "baseline": BASELINE_COMMIT, "reason": "git diff failed"}
        (self.aux / "protected-files-diff.txt").write_text(diff.stdout, encoding="utf-8", newline="\n")
        return {"available": True, "baseline": BASELINE_COMMIT, "paths": list(PROTECTED_PATHS), "diff_empty": diff.stdout.strip() == ""}

    # ---- agent steps -------------------------------------------------------------------
    def wait_agent_up(self, timeout: float = 60) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                status, _ = http("GET", self.base + "/environment/status", timeout=3)
                if status == 200:
                    return
            except OSError:
                pass
            if self.agent.proc is not None and self.agent.proc.poll() is not None:
                raise StepFailure(f"agent exited (code {self.agent.proc.returncode}) before serving requests")
            time.sleep(0.5)
        raise StepFailure("agent did not start serving /environment/status in time")

    def pair(self, code: str) -> None:
        status, body = http("POST", self.base + "/session/pair", headers=self.headers(False), body={"code": code})
        if status != 200:
            raise StepFailure(f"pairing failed: HTTP {status}")
        self.token = json.loads(body)["token"]  # never written to disk
        self.result["pairing"] = {"paired": True}

    def prepare(self) -> None:
        outcome: dict[str, object] = {}

        def call() -> None:
            outcome["status"], outcome["body"] = http(
                "POST", self.base + "/environment/prepare", headers=self.headers(), timeout=self.args.prepare_timeout + 60
            )

        thread = threading.Thread(target=call, daemon=True)
        thread.start()
        polls: list[dict[str, str]] = []
        deadline = time.monotonic() + self.args.prepare_timeout
        final: dict[str, object] = {}
        while time.monotonic() < deadline:
            final = self.get_json("/environment/status")
            entry = {"status": str(final.get("status")), "reason": str(final.get("reason"))}
            if not polls or polls[-1] != entry:
                polls.append(entry)
            if not thread.is_alive():  # prepare call returned: the status polled just now is final
                break
            time.sleep(2)
        thread.join(timeout=5)
        write_json(self.aux / "environment-status-poll.json", polls)
        write_json(self.aux / "environment-status-final.json", final)
        if "body" in outcome:
            try:
                write_json(self.aux / "environment-prepare-response.json", json.loads(outcome["body"]))
            except ValueError:
                pass
        self.result["environment"] = {
            "final_status": final.get("status"), "reason": final.get("reason"), "prepare_http_status": outcome.get("status"),
        }
        if final.get("status") != "READY":
            raise StepFailure(f"environment did not reach READY (status={final.get('status')}, reason={final.get('reason')})")

    def build(self, label: str, source: str, lib_deps: list[str], fetch_artifacts: bool) -> None:
        record: dict[str, object] = {"lib_deps": lib_deps, "build_id": None, "final_status": None, "error": None, "artifacts": []}
        self.result["builds"][label] = record  # type: ignore[index]
        payload = {"source_code": source, "board": "esp32dev", "framework": "arduino", "lib_deps": lib_deps}
        status, body = http("POST", self.base + "/build", headers=self.headers(), body=payload)
        if status != 200:
            raise StepFailure(f"{label}: POST /build -> HTTP {status}: {body[:200]!r}")
        build_id = json.loads(body)["build_id"]
        record["build_id"] = build_id
        deadline = time.monotonic() + self.args.build_timeout
        info: dict[str, object] = {}
        while time.monotonic() < deadline:
            info = self.get_json(f"/build/{build_id}/status", auth=True)
            if info.get("status") in TERMINAL_BUILD:
                break
            time.sleep(2)
        write_json(self.aux / f"build-{label}-status.json", info)
        record["final_status"], record["error"] = info.get("status"), info.get("error")
        log_status, log_body = http("GET", f"{self.base}/build/{build_id}/log", headers=self.headers())
        if log_status == 200:
            (self.out / f"build-{label}.log").write_bytes(log_body)
            record["log_file"] = f"build-{label}.log"
        if info.get("status") not in TERMINAL_BUILD:
            raise StepFailure(f"{label}: build did not finish within {self.args.build_timeout}s")
        if info.get("status") != "SUCCEEDED":
            raise StepFailure(f"{label}: build {info.get('status')}: {info.get('error')}")
        if fetch_artifacts:
            for name in DHT_ARTIFACTS:
                code, data = http("GET", f"{self.base}/build/{build_id}/firmware/{name}", headers=self.headers(), timeout=120)
                if code != 200:
                    raise StepFailure(f"{label}: artifact {name} -> HTTP {code}")
                (self.out / name).write_bytes(data)
                record["artifacts"].append(name)  # type: ignore[union-attr]
            write_json(self.aux / "merge-sources.json", self.collect_merge_sources(build_id))

    # ---- orchestration -----------------------------------------------------------------
    def run(self) -> int:
        args = self.args
        if not self.python.is_file():
            print(f"error: agent Python not found: {self.python}", file=sys.stderr)
            return 2
        if port_in_use(args.port):
            print(f"error: port {args.port} is already in use; refusing to drive an unknown agent", file=sys.stderr)
            return 2
        self.aux.mkdir(parents=True, exist_ok=True)
        fingerprint = {"before": self.base_fingerprint()}
        ok = True
        try:
            self.agent.start()
            self.step("agent-start", "ok", " ".join(self.agent.command))
            code = self.agent.wait_pairing_code(60)
            self.step("pairing-code", "ok", "parsed from agent stdout")
            self.wait_agent_up()
            boards = self.get_json("/boards")
            frameworks = self.get_json("/frameworks")
            board = next(b["id"] for b in boards if b.get("default"))
            framework = next(f["id"] for f in frameworks if f.get("default"))
            self.write_run_metadata(board, framework)
            self.step("run-metadata", "ok")
            self.pair(code)
            self.step("pair", "ok")
            self.prepare()
            self.step("prepare", "ok", "READY")
            self.build("blink", BLINK_SOURCE, [], fetch_artifacts=False)
            self.step("build-blink", "ok", "SUCCEEDED (binaries intentionally not retained)")
            self.build("dht", DHT_SOURCE, [FROZEN_DHT_SPEC], fetch_artifacts=True)
            self.step("build-dht", "ok", "SUCCEEDED, artifacts downloaded")
        except (StepFailure, OSError, ValueError, KeyError, StopIteration) as exc:
            ok = False
            self.step("failure", "failed", f"{type(exc).__name__}: {exc}")
        finally:
            self.agent.stop()
            released = False
            for _ in range(25):
                if not port_in_use(args.port):
                    released = True
                    break
                time.sleep(0.2)
            fingerprint["after"] = self.base_fingerprint()
            write_json(self.aux / "base-fingerprint.json", fingerprint)
            write_json(self.aux / "backend-inference.json", self.infer_backend())
            write_json(self.aux / "protected-files-check.json", self.protected_check())
            lifecycle_clean = self.agent.clean_exit() and released
            self.result["agent"] = {
                "command": [Path(self.agent.command[0]).name, *self.agent.command[1:]],
                "pairing_code_found": self.agent.pairing_code is not None,
                "shutdown": self.agent.shutdown, "exit_code": self.agent.exit_code,
                "port": args.port, "port_released": released, "lifecycle_clean": lifecycle_clean,
            }
            if not lifecycle_clean:
                ok = False
                self.step("agent-lifecycle", "failed", f"shutdown={self.agent.shutdown} exit={self.agent.exit_code} port_released={released}")
            else:
                self.step("agent-lifecycle", "ok", f"shutdown={self.agent.shutdown} exit={self.agent.exit_code}")
            self.result["ok"] = ok
            self.result["steps"] = self.steps
            write_json(self.aux / "driver-result.json", self.result)
        return 0 if ok else 1


def copy_provisioning(args: argparse.Namespace) -> int:
    source = Path(args.workspace_root).resolve() / PROVISION_EVIDENCE
    if not source.is_file():
        print(f"BLOCKED: provisioning evidence not found: {source} (provision-windows-base.ps1 has not run here)", file=sys.stderr)
        return 3
    dest = Path(args.dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    print(f"copied {source} -> {dest} (sha256 {sha256_file(dest)})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="drive the Local Agent and collect evidence")
    run.add_argument("--out", required=True, help="output m24/ directory (created if missing)")
    run.add_argument("--workspace-root", default=str(default_workspace()))
    run.add_argument("--python", help="Python used to start the agent (default: local-agent/venv)")
    run.add_argument("--port", type=int, default=8765)
    run.add_argument("--origin", default="http://localhost:3000", help="Origin header; must be in the agent allowlist")
    run.add_argument("--prepare-timeout", type=int, default=900)
    run.add_argument("--build-timeout", type=int, default=900)
    copy = sub.add_parser("copy-provisioning", help="copy the fixed-path provisioning JSON to --dest")
    copy.add_argument("--workspace-root", default=str(default_workspace()))
    copy.add_argument("--dest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "copy-provisioning":
        return copy_provisioning(args)
    return Driver(args).run()


if __name__ == "__main__":
    sys.exit(main())
