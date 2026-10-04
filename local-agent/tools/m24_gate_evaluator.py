#!/usr/bin/env python3
"""M2.4 gate evaluator: turns an `m24/` evidence directory into gate-result.json and sha256.txt.

Evaluates the gates frozen in docs/PROJECT_STATE.md (G0, G1-CI, G1-FINAL, G2, G3, G4, G5) and a derived RC aggregate.
Every criterion is PASS, FAIL or BLOCKED and cites evidence paths (relative to the m24 directory; `repo:` prefix = a file
in the checkout) or an explicit reason. Missing evidence is never PASS; a PASS/FAIL without an existing evidence file is
rejected by the evaluator itself.

Order of output (rule): supplementary derived evidence under aux/evaluator/ -> gate-result.json -> sha256.txt.
sha256.txt is generated LAST. It hashes every file under the m24 directory EXCEPT sha256.txt itself, one
`<sha256>  <relative/posix/path>` line per file, sorted by path, LF line endings. Use --no-seal to skip it.

gate-result.json is deterministic: sorted keys, no timestamps, no absolute paths.

Exit codes: 0 evaluated and no FAIL (BLOCKED does not change the exit code), 1 at least one FAIL, 2 usage error.

Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

CONTRACT_COMMIT = "3fc628f"
FROZEN_DHT_SPEC = "adafruit/DHT sensor library@1.4.4"
FROZEN_BOARD, FROZEN_FRAMEWORK = "esp32dev", "arduino"
# Frozen contract (docs/PROJECT_STATE.md, G2): environment.py must not depend directly on these POSIX primitives.
FORBIDDEN_POSIX = ("unshare", "mount", "killpg", "SIGKILL", "subprocess")
ENVIRONMENT_PY = "local-agent/app/environment.py"
PROVISION_SCRIPT = "local-agent/tools/provision-windows-base.ps1"
M24_REPORT = "Eksperiment/validation/m2.4-validation-2026-09-30.md"
REQUIRED_METADATA = (
    "commit_sha", "runner_os", "runner_arch", "python_version", "platformio_version", "board", "framework", "timestamp",
)
CONTRACT_FILES = (
    "run-metadata.json", "gate-result.json", "provisioning-run-1.log", "provisioning-run-2.log",
    "provisioning-fingerprint-before.json", "provisioning-fingerprint-after.json", "build-blink.log", "build-dht.log",
    "firmware.bin", "firmware.elf", "wokwi-firmware.bin", "sha256.txt",
)
GATES = ("G0", "G1-CI", "G1-FINAL", "G2", "G3", "G4", "G5")
PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"
SECTION_RE = re.compile(r"(?m)^\[CompilerIO[^\]]*\].*$")
# PlatformIO package-manager activity in a provisioning log. The script's own "Installing <spec> ..." lines are not matched.
PIO_ACTIVITY_RE = re.compile(r"(?m)^\s*(?:(?:Tool|Platform|Library|Package) Manager:\s*)?(?:Downloading|Installing)\b.*$")
SCRIPT_INSTALL_LINE_RE = re.compile(r"^\s*Installing \S+@\S+ \.\.\.\s*$")


class Crit:
    def __init__(self, cid: str, text: str, status: str, etype: str, evidence: list[str], reason: str) -> None:
        self.cid, self.text, self.status, self.etype, self.evidence, self.reason = cid, text, status, etype, evidence, reason

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.cid, "description": self.text, "status": self.status, "evidence_type": self.etype,
            "evidence": sorted(set(self.evidence)), "reason": self.reason,
        }


class Ev:
    """One measured check: status + evidence paths + reason."""

    def __init__(self, status: str, evidence: list[str], reason: str) -> None:
        self.status, self.evidence, self.reason = status, evidence, reason


def combine(statuses: list[str]) -> str:
    if FAIL in statuses:
        return FAIL
    return PASS if statuses and all(s == PASS for s in statuses) else BLOCKED


class Evaluator:
    def __init__(self, m24: Path, workspace: Path) -> None:
        self.m24, self.ws = m24, workspace
        self.meta = self.load("run-metadata.json")
        self.driver = self.load("aux/driver-result.json")
        meta = self.meta or {}
        self.host = {"Linux": "linux", "Windows": "windows"}.get(str(meta.get("host_os")), str(meta.get("host_os")).lower())
        self.ci = bool(meta.get("ci")) and bool(meta.get("runner_os")) and bool(meta.get("runner_arch"))
        self.etype = "CI" if self.ci else "RUNTIME"
        self.windows_x64 = self.host == "windows" and str(meta.get("host_arch", "")).upper() in ("AMD64", "X86_64")

    # ---- file helpers ------------------------------------------------------------------
    def has(self, rel: str) -> bool:
        return (self.m24 / rel).is_file()

    def load(self, rel: str):
        path = self.m24 / rel
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return None

    def read(self, rel: str) -> bytes | None:
        path = self.m24 / rel
        return path.read_bytes() if path.is_file() else None

    def write_aux(self, name: str, data: object) -> str:
        rel = f"aux/evaluator/{name}"
        target = self.m24 / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
        return rel

    def missing(self, *rels: str) -> list[str]:
        return [rel for rel in rels if not self.has(rel)]

    # ---- individual checks -------------------------------------------------------------
    def check_metadata(self) -> Ev:
        if self.meta is None:
            return Ev(BLOCKED, [], "run-metadata.json is missing or not valid JSON")
        absent = [key for key in REQUIRED_METADATA if key not in self.meta]
        if absent:
            return Ev(FAIL, ["run-metadata.json"], f"required fields absent: {absent}")
        null = [key for key in REQUIRED_METADATA if self.meta[key] is None]
        if null:
            return Ev(BLOCKED, ["run-metadata.json"], f"CI-specific or unavailable values are null: {null}")
        return Ev(PASS, ["run-metadata.json"], "all required fields present")

    def check_prepare(self) -> Ev:
        if self.driver is None:
            return Ev(BLOCKED, [], "aux/driver-result.json missing: the agent was not driven")
        env = self.driver.get("environment", {})
        evidence = [p for p in ("aux/driver-result.json", "aux/environment-status-final.json", "aux/environment-status-poll.json") if self.has(p)]
        if env.get("final_status") == "READY":
            return Ev(PASS, evidence, "/environment/prepare reached READY")
        if env.get("final_status") is None:
            return Ev(BLOCKED, evidence, "prepare was not reached")
        return Ev(FAIL, evidence, f"environment status {env.get('final_status')}: {env.get('reason')}")

    def check_build(self, label: str) -> Ev:
        if self.driver is None:
            return Ev(BLOCKED, [], "aux/driver-result.json missing")
        build = self.driver.get("builds", {}).get(label)
        evidence = [p for p in (f"build-{label}.log", f"aux/build-{label}-status.json", "aux/driver-result.json") if self.has(p)]
        if build is None:
            return Ev(BLOCKED, evidence, f"{label} build was not attempted")
        if build.get("final_status") == "SUCCEEDED" and self.has(f"build-{label}.log"):
            return Ev(PASS, evidence, f"{label} build SUCCEEDED")
        return Ev(FAIL, evidence, f"{label} build {build.get('final_status')}: {build.get('error')}")

    def check_dht_spec(self) -> Ev:
        build = (self.driver or {}).get("builds", {}).get("dht")
        if build is None:
            return Ev(BLOCKED, [], "DHT build was not attempted")
        if build.get("lib_deps") == [FROZEN_DHT_SPEC]:
            return Ev(PASS, ["aux/driver-result.json"], f"DHT build used exactly {FROZEN_DHT_SPEC!r}")
        return Ev(FAIL, ["aux/driver-result.json"], f"DHT lib_deps {build.get('lib_deps')} != [{FROZEN_DHT_SPEC!r}]")

    def check_artifacts(self) -> Ev:
        names = ("firmware.bin", "firmware.elf", "wokwi-firmware.bin")
        absent = self.missing(*names)
        if absent:
            return Ev(BLOCKED, [n for n in names if self.has(n)], f"artifacts not collected: {absent}")
        fw, elf, merged = self.read("firmware.bin"), self.read("firmware.elf"), self.read("wokwi-firmware.bin")
        problems = []
        if not fw or fw[0] != 0xE9:
            problems.append("firmware.bin does not start with the ESP image magic 0xE9")
        if not elf or elf[:4] != b"\x7fELF":
            problems.append("firmware.elf is not an ELF file")
        if not merged:
            problems.append("wokwi-firmware.bin is empty")
        sizes = {n: len(self.read(n) or b"") for n in names}
        rel = self.write_aux("artifact-structure.json", {"sizes_bytes": sizes, "problems": problems})
        return Ev(FAIL if problems else PASS, [*names, rel], "; ".join(problems) or "three artifacts present with expected structure")

    def check_offsets(self) -> Ev:
        fw, merged = self.read("firmware.bin"), self.read("wokwi-firmware.bin")
        if fw is None or merged is None:
            return Ev(BLOCKED, [n for n in ("firmware.bin", "wokwi-firmware.bin") if self.has(n)], "firmware.bin / wokwi-firmware.bin not collected")
        checks: dict[str, object] = {
            "bytes_0x0000_0x0FFF_all_0xFF": len(merged) >= 0x1000 and merged[:0x1000] == b"\xff" * 0x1000,
            "firmware_identical_at_0x10000": merged[0x10000:0x10000 + len(fw)] == fw and len(merged) >= 0x10000 + len(fw),
        }
        sources = self.load("aux/merge-sources.json")
        files = (sources or {}).get("files", {})
        evidence = ["firmware.bin", "wokwi-firmware.bin"]
        for name, offset in (("bootloader.bin", 0x1000), ("partitions.bin", 0x8000)):
            info = files.get(name)
            if info:
                evidence.append("aux/merge-sources.json")
                slice_ = merged[offset:offset + info["size"]]
                checks[f"{name}_identical_at_{offset:#x}"] = hashlib.sha256(slice_).hexdigest() == info["sha256"]
            else:
                checks[f"{name}_source_hash_unavailable_magic_only_at_{offset:#x}"] = (
                    merged[offset:offset + 1] == b"\xe9" if offset == 0x1000 else merged[offset:offset + 2] == b"\xaa\x50"
                )
        firmware_src = files.get("firmware.bin")
        if firmware_src:
            checks["firmware_collected_equals_build_dir_firmware"] = hashlib.sha256(fw).hexdigest() == firmware_src["sha256"]
        rel = self.write_aux("merge-offsets.json", {
            "offsets": {"bootloader": "0x1000", "partitions": "0x8000", "firmware": "0x10000"}, "checks": checks,
        })
        failed = sorted(name for name, passed in checks.items() if not passed)
        return Ev(FAIL if failed else PASS, [*sorted(set(evidence)), rel], f"failed: {failed}" if failed else "byte-level offset checks passed")

    def check_compile_clean(self) -> Ev:
        report, evidence, problems, unseen = {}, [], [], []
        for label in ("blink", "dht"):
            raw = self.read(f"build-{label}.log")
            if raw is None:
                unseen.append(f"build-{label}.log missing")
                continue
            evidence.append(f"build-{label}.log")
            text = raw.decode("utf-8", errors="replace")
            marks = list(SECTION_RE.finditer(text))
            compile_text, found = "", False
            for i, mark in enumerate(marks):
                if mark.group(0).strip() == "[CompilerIO] Compilation":
                    found = True
                    end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
                    compile_text += text[mark.end():end]
            counts = {"Downloading": compile_text.count("Downloading"), "Installing": compile_text.count("Installing")}
            report[label] = {"compilation_section_found": found, "compilation_section_chars": len(compile_text), **counts}
            if not found:
                unseen.append(f"{label}: no '[CompilerIO] Compilation' section (build did not reach compile)")
            elif counts["Downloading"] or counts["Installing"]:
                problems.append(f"{label}: {counts}")
        evidence.append(self.write_aux("compile-sections.json", report))
        if problems:
            return Ev(FAIL, evidence, "; ".join(problems))
        if unseen:
            return Ev(BLOCKED, evidence, "; ".join(unseen))
        return Ev(PASS, evidence, "no 'Downloading'/'Installing' in either Compilation section (dependency sections not examined)")

    def check_backend(self) -> Ev:
        info = self.load("aux/backend-inference.json")
        if info is None:
            return Ev(BLOCKED, [], "aux/backend-inference.json missing")
        ok = info.get("inferred_backend") == info.get("expected_backend") != "undetermined"
        reason = f"inferred {info.get('inferred_backend')}, expected {info.get('expected_backend')} (filesystem inference; API does not report the backend)"
        return Ev(PASS if ok else FAIL, ["aux/backend-inference.json"], reason)

    def check_lifecycle(self) -> Ev:
        agent = (self.driver or {}).get("agent")
        if not agent:
            return Ev(BLOCKED, [], "aux/driver-result.json missing")
        ok = bool(agent.get("lifecycle_clean"))
        return Ev(PASS if ok else FAIL, ["aux/driver-result.json"], f"shutdown={agent.get('shutdown')} exit={agent.get('exit_code')} port_released={agent.get('port_released')}")

    def check_base_fingerprint(self) -> Ev:
        data = self.load("aux/base-fingerprint.json")
        if data is None:
            return Ev(BLOCKED, [], "aux/base-fingerprint.json missing")
        before, after = data.get("before", {}), data.get("after", {})
        if not (before.get("available") and after.get("available")):
            return Ev(BLOCKED, ["aux/base-fingerprint.json"], f"fingerprint unavailable: {before.get('reason') or after.get('reason')}")
        same = before["sha256"] == after["sha256"]
        return Ev(PASS if same else FAIL, ["aux/base-fingerprint.json"], "Linux Base fingerprint unchanged across the run" if same else "Linux Base fingerprint changed")

    def check_protected(self) -> Ev:
        data = self.load("aux/protected-files-check.json")
        if data is None:
            return Ev(BLOCKED, [], "aux/protected-files-check.json missing")
        if not data.get("available"):
            return Ev(BLOCKED, ["aux/protected-files-check.json"], f"cannot compare to {data.get('baseline')}: {data.get('reason')}")
        evidence = ["aux/protected-files-check.json"] + (["aux/protected-files-diff.txt"] if self.has("aux/protected-files-diff.txt") else [])
        return Ev(PASS if data.get("diff_empty") else FAIL, evidence, f"diff of protected paths vs {data['baseline']} is {'empty' if data.get('diff_empty') else 'NOT empty'}")

    def check_static_posix(self) -> Ev:
        path = self.ws / ENVIRONMENT_PY
        if not path.is_file():
            return Ev(BLOCKED, [], f"{ENVIRONMENT_PY} not found under the workspace root")
        raw = path.read_bytes()
        hits = []
        for number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
            for token in FORBIDDEN_POSIX:
                if re.search(rf"\b{token}\b", line):
                    hits.append({"line": number, "token": token, "text": line.strip()})
        rel = self.write_aux("g2-static-scan.json", {
            "file": ENVIRONMENT_PY, "sha256": hashlib.sha256(raw).hexdigest(), "forbidden_tokens": list(FORBIDDEN_POSIX), "hits": hits,
        })
        return Ev(FAIL if hits else PASS, [rel], f"{len(hits)} forbidden token hit(s)" if hits else "no forbidden POSIX primitives in environment.py")

    def check_pins(self) -> Ev:
        script = self.ws / PROVISION_SCRIPT
        if not script.is_file():
            return Ev(BLOCKED, [], f"{PROVISION_SCRIPT} not found: no pinned versions to compare against")
        text = script.read_text(encoding="utf-8", errors="replace")
        pins = {
            m.group("dir").replace("\\", "/"): m.group("ver")
            for m in re.finditer(r"Spec\s*=\s*'[^']+';\s*Dir\s*=\s*'(?P<dir>[^']+)';\s*Version\s*=\s*'(?P<ver>[^']+)'", text)
        }
        pio_pin = re.search(r"\$PioVersion\s*=\s*'([^']+)'", text)
        base = self.ws / "runtime" / "platformio-data"
        observed, problems = {}, []
        for rel_dir, pinned in sorted(pins.items()):
            meta_file = next((base / rel_dir / n for n in ("platform.json", "package.json") if (base / rel_dir / n).is_file()), None)
            version = json.loads(meta_file.read_text(encoding="utf-8")).get("version") if meta_file else None
            observed[rel_dir] = {"pinned": pinned, "observed": version}
            if version is None:
                problems.append(f"{rel_dir}: not installed in the Base")
            elif version != pinned:
                problems.append(f"{rel_dir}: {version} != {pinned}")
        pio_obs = (self.meta or {}).get("platformio_version")
        observed["platformio-core"] = {"pinned": pio_pin.group(1) if pio_pin else None, "observed": pio_obs}
        if not pio_pin or pio_obs != pio_pin.group(1):
            problems.append(f"platformio core {pio_obs} != {pio_pin.group(1) if pio_pin else None}")
        rel = self.write_aux("g5-pinned-versions.json", {
            "pins_source": PROVISION_SCRIPT, "observed_source": "runtime/platformio-data/*/package.json|platform.json + run-metadata.json",
            "versions": observed, "problems": problems,
        })
        if not pins:
            return Ev(BLOCKED, [rel], "no pins could be parsed from the provisioning script")
        return Ev(FAIL if problems else PASS, [rel, "run-metadata.json"], "; ".join(problems) or "package, toolchain and PlatformIO versions equal the pinned set")

    def check_board_framework(self) -> Ev:
        if self.meta is None:
            return Ev(BLOCKED, [], "run-metadata.json missing")
        ok = self.meta.get("board") == FROZEN_BOARD and self.meta.get("framework") == FROZEN_FRAMEWORK
        return Ev(PASS if ok else FAIL, ["run-metadata.json"], f"board={self.meta.get('board')} framework={self.meta.get('framework')}")

    def check_provisioning(self) -> Ev:
        required = ("provisioning-run-1.log", "provisioning-run-2.log", "provisioning-fingerprint-before.json", "provisioning-fingerprint-after.json")
        absent = self.missing(*required)
        if absent:
            return Ev(BLOCKED, [r for r in required if self.has(r)], f"provisioning evidence not present (script not run in this evidence set): {absent}")
        before, after = self.load(required[2]), self.load(required[3])
        if before is None or after is None:
            return Ev(FAIL, list(required), "fingerprint file is not valid JSON")
        problems, report = [], {}
        for label, doc in (("before", before), ("after", after)):
            os_name = str((doc.get("host") or {}).get("os", ""))
            if "windows" not in os_name.lower():
                problems.append(f"{label}: host.os {os_name!r} is not a Windows provisioning record (Linux fingerprints are never compared)")
        for key in ("listing_sha256", "file_count", "packages"):
            same = before.get(key) == after.get(key)
            report[key] = {"equal": same}
            if not same:
                problems.append(f"{key} differs between run 1 and run 2")
        if str(after.get("provisioned_at", "")) <= str(before.get("provisioned_at", "")):
            problems.append("after.provisioned_at is not later than before.provisioned_at (same run copied twice?)")
        for log in required[:2]:
            if b"PROVISIONING OK" not in (self.read(log) or b""):
                problems.append(f"{log}: no 'PROVISIONING OK' line")
        run2 = (self.read(required[1]) or b"").decode("utf-8", errors="replace")
        activity = [ln.strip() for ln in PIO_ACTIVITY_RE.findall(run2) if not SCRIPT_INSTALL_LINE_RE.match(ln)]
        report["run2_package_manager_activity_lines"] = activity
        if activity:
            problems.append(f"run 2 log shows package manager activity ({len(activity)} line(s)): possible reinstall")
        rel = self.write_aux("provisioning-comparison.json", {
            "criteria": "fingerprint docs equal on listing_sha256/file_count/packages (never provisioned_at/computer); run 2 log has "
                        "no PlatformIO Downloading/Installing lines (the script's own 'Installing <spec> ...' lines are excluded)",
            "report": report, "problems": problems,
        })
        return Ev(FAIL if problems else PASS, [*required, rel], "; ".join(problems) or "run 2 did not reinstall or mutate the Base")

    def check_local_report(self) -> Ev:
        path = self.ws / M24_REPORT
        if not path.is_file():
            return Ev(BLOCKED, [], f"{M24_REPORT} not present in this checkout")
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\|\s*G4 Linux regression\s*\|\s*\*\*PASS\*\*", text):
            return Ev(PASS, [f"repo:{M24_REPORT}"], "recorded local RUNTIME G4 PASS (document, not machine-verified by this tool)")
        return Ev(BLOCKED, [f"repo:{M24_REPORT}"], "report does not record G4 PASS")

    # ---- gates -------------------------------------------------------------------------
    def applicable(self, ok: bool, reason: str, ev: Ev) -> Ev:
        return ev if ok else Ev(BLOCKED, ev.evidence, reason)

    def evaluate(self) -> dict[str, object]:
        linux, win_ci = self.host == "linux", self.windows_x64 and self.ci
        ct = self.etype
        c = {k: getattr(self, f"check_{k}")() for k in (
            "prepare", "dht_spec", "artifacts", "offsets", "compile_clean", "backend", "lifecycle", "base_fingerprint",
            "protected", "static_posix", "pins", "board_framework", "provisioning", "local_report",
        )}
        blink, dht = self.check_build("blink"), self.check_build("dht")
        run_set = [c["prepare"], blink, dht, c["dht_spec"], c["artifacts"], c["offsets"], c["compile_clean"], c["backend"], c["lifecycle"]]

        def merge(name: str, evs: list[Ev]) -> Ev:
            status = combine([e.status for e in evs])
            return Ev(status, [p for e in evs for p in e.evidence], f"{name}: " + ", ".join(sorted({e.status for e in evs})))

        build_set = merge("blink+DHT builds, artifacts, offsets, compile section",
                          [blink, dht, c["dht_spec"], c["artifacts"], c["offsets"], c["compile_clean"]])
        runtime_set = merge("prepare, builds, artifacts, backend inference, lifecycle", run_set)
        no_win = f"requires a native Windows x64 GitHub runner; this run: host={self.host}, ci={self.ci}"
        no_lin = f"Linux gate; this run: host={self.host}"
        crits: dict[str, list[Crit]] = {g: [] for g in GATES}

        def add(gate: str, cid: str, text: str, ev: Ev, etype: str) -> None:
            crits[gate].append(Crit(cid, text, ev.status, etype, ev.evidence, ev.reason))

        blocked = lambda reason: Ev(BLOCKED, [], reason)  # noqa: E731
        # G0
        add("G0", "G0.1", "Linux Base fingerprint unchanged", self.applicable(linux, no_lin, c["base_fingerprint"]), ct)
        add("G0", "G0.2", "Protected files unchanged vs ccbcc91", self.applicable(linux, no_lin, c["protected"]), ct)
        # G1-CI
        add("G1-CI", "G1-CI.1", "Provisioning idempotent within one job (run 2: no reinstall/mutation)", self.applicable(win_ci, no_win, c["provisioning"]), "CI")
        add("G1-CI", "G1-CI.2", "Prepare, blink + DHT builds, artifacts, offsets, offline compile section, backend, lifecycle", self.applicable(win_ci, no_win, runtime_set), "CI")
        # G1-FINAL / G3
        add("G1-FINAL", "G1-FINAL.1", "Same flow on the physical target Windows host", blocked("requires the physical Windows target host; this tool cannot attest host identity"), "RUNTIME")
        add("G3", "G3.1", "Windows Personal E2E on a physical host with the public staging Web App", blocked("final release gate: needs physical Windows host + public staging Web App; not drivable by m24_agent_driver; a CI runner never satisfies G3"), "RUNTIME")
        # G2
        add("G2", "G2.1", "environment.py has no direct POSIX primitives", c["static_posix"], "CODE")
        add("G2", "G2.2", "Linux ExecutionBackend runs prepare/builds", self.applicable(linux, no_lin, runtime_set), ct)
        add("G2", "G2.3", "Windows ExecutionBackend CI runtime", self.applicable(win_ci, no_win, runtime_set), "CI")
        add("G2", "G2.4", "Windows ExecutionBackend target-host runtime", blocked("blocked until G1-FINAL (physical Windows host)"), "RUNTIME")
        # G4
        add("G4", "G4.1", "Blink + DHT builds, artifacts, offsets, offline compile section on Linux", self.applicable(linux, no_lin, build_set), ct)
        add("G4", "G4.2", "Linux Base fingerprint unchanged", self.applicable(linux, no_lin, c["base_fingerprint"]), ct)
        add("G4", "G4.3", "Automated Linux CI regression executed", self.applicable(linux and self.ci, f"requires a Linux GitHub runner; this run: host={self.host}, ci={self.ci}", build_set), "CI")
        add("G4", "G4.4", "Existing local RUNTIME regression evidence (network probe, backend/agent timeout, Hub paths)", c["local_report"], "RUNTIME")
        add("G4", "G4.5", "Network probe, backend/agent timeout and Hub checks re-exercised by this tool", blocked("not exercised by m24_agent_driver"), ct)
        # G5
        add("G5", "G5.1", "Board and framework match (esp32dev / arduino)", c["board_framework"], ct)
        add("G5", "G5.2", "Package, toolchain and PlatformIO versions equal the pinned set", c["pins"], ct)
        add("G5", "G5.3", "Merge offsets bootloader 0x1000 / partitions 0x8000 / firmware 0x10000, 0x0-0xFFF = 0xFF", c["offsets"], ct)
        add("G5", "G5.4", "Artifact structure (firmware.bin, firmware.elf, wokwi-firmware.bin)", c["artifacts"], ct)
        add("G5", "G5.5", "Linux and Windows evidence sets compared", blocked("single-host evidence set; cross-host comparison needs the peer host's m24 set (not supported in this iteration)"), ct)

        gates = {}
        for gate in GATES:
            gates[gate] = {"status": combine([cr.status for cr in crits[gate]]), "criteria": [cr.as_dict() for cr in crits[gate]]}
        statuses = [g["status"] for g in gates.values()]  # type: ignore[index]
        rc = combine(statuses)
        return {
            "schema": "compilerio.m24.gate-result/1",
            "contract_commit": CONTRACT_COMMIT,
            "run": {
                "evidence_class": self.etype, "host_os": (self.meta or {}).get("host_os"), "host_arch": (self.meta or {}).get("host_arch"),
                "ci": self.ci, "commit_sha": (self.meta or {}).get("commit_sha"), "worktree_dirty": (self.meta or {}).get("worktree_dirty"),
                "metadata": {"status": self.check_metadata().status, "reason": self.check_metadata().reason},
            },
            "artifact_inventory": {name: ("present" if self.has(name) else "missing") for name in CONTRACT_FILES if name not in ("gate-result.json", "sha256.txt")},
            "gates": gates,
            "rc": {
                "status": rc,
                "gate_statuses": {g: gates[g]["status"] for g in GATES},  # type: ignore[index]
                "note": "derived aggregate: PASS only if every gate PASS; one evidence set covers one host",
            },
        }


def validate_result(result: dict[str, object], m24: Path, ws: Path) -> list[str]:
    """Self-check: PASS/FAIL need existing evidence; BLOCKED needs a reason; no unknown statuses."""
    problems = []
    for gate, body in result["gates"].items():  # type: ignore[union-attr]
        for crit in body["criteria"]:
            where = crit["id"]
            if crit["status"] not in (PASS, FAIL, BLOCKED):
                problems.append(f"{where}: invalid status {crit['status']}")
            if crit["status"] in (PASS, FAIL) and not crit["evidence"]:
                problems.append(f"{where}: {crit['status']} without evidence")
            if crit["status"] == BLOCKED and not crit["reason"]:
                problems.append(f"{where}: BLOCKED without reason")
            for path in crit["evidence"]:
                target = ws / path[5:] if path.startswith("repo:") else m24 / path
                if not target.is_file():
                    problems.append(f"{where}: evidence path does not exist: {path}")
    return problems


def seal(m24: Path) -> list[str]:
    files = sorted((p for p in m24.rglob("*") if p.is_file() and p.relative_to(m24).as_posix() != "sha256.txt"), key=lambda p: p.relative_to(m24).as_posix())
    lines = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(m24).as_posix()}")
    (m24 / "sha256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--m24-dir", required=True, help="evidence directory produced by m24_agent_driver.py")
    parser.add_argument("--workspace-root", default=str(Path(__file__).resolve().parents[2]), help="checkout root (environment.py, provisioning script, Base)")
    parser.add_argument("--no-seal", action="store_true", help="do not write sha256.txt")
    args = parser.parse_args(argv)
    m24, ws = Path(args.m24_dir).resolve(), Path(args.workspace_root).resolve()
    if not m24.is_dir():
        print(f"error: {m24} is not a directory", file=sys.stderr)
        return 2
    (m24 / "sha256.txt").unlink(missing_ok=True)  # stale seal from an earlier evaluation must not be hashed or trusted
    result = Evaluator(m24, ws).evaluate()
    problems = validate_result(result, m24, ws)
    if problems:
        print("internal consistency errors:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    (m24 / "gate-result.json").write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    if not args.no_seal:
        seal(m24)
    for gate, body in result["gates"].items():  # type: ignore[union-attr]
        print(f"{gate:9} {body['status']}")
        for crit in body["criteria"]:
            print(f"  {crit['id']:11} {crit['status']:8} {crit['description']}" + (f"  [{crit['reason']}]" if crit["status"] != PASS else ""))
    print(f"{'RC':9} {result['rc']['status']}")  # type: ignore[index]
    return 1 if any(b["status"] == FAIL for b in result["gates"].values()) else 0  # type: ignore[union-attr]


if __name__ == "__main__":
    sys.exit(main())
