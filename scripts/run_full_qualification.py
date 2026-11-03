#!/usr/bin/env python3
"""Unified MORPH V2 engineering qualification runner.

Run from any directory inside the MORPH checkout:
  python3 scripts/run_full_qualification.py --github-run-id <GDS workflow run id>

The runner executes the local contract, Python regression, TinyTapeout RTL
simulation, Yosys synthesis and structural CDC checks. It then validates the
CTS4/SDC settings in a completed TinyTapeout GDS artifact and invokes the
project's final physical-signoff checker.

A GDS build is deliberately not launched by this script: the repository's
IHP/LibreLane flow is currently run by the TinyTapeout GitHub Actions job.
The script consumes that job's GDS_logs artifact, or an already-extracted
reports directory supplied with --reports-dir.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


class BlockedStage(RuntimeError):
    """A stage could not run because a required tool/artifact is unavailable."""


class Qualification:
    def __init__(self, root: Path, args: argparse.Namespace) -> None:
        self.root = root
        self.args = args
        self.build_dir = root / "build" / "qualification"
        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.python = Path(sys.executable)
        self.results: list[dict[str, Any]] = []
        self.started = dt.datetime.now(dt.timezone.utc).isoformat()

    @staticmethod
    def utc_now() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat()

    def stage(self, name: str, fn) -> None:
        print(f"\n{'=' * 76}\nSTAGE: {name}\n{'=' * 76}", flush=True)
        started = time.monotonic()
        result: dict[str, Any] = {
            "name": name,
            "started_at": self.utc_now(),
            "status": "FAIL",
        }
        try:
            details = fn() or {}
            result.update(details)
            result["status"] = "PASS"
            print(f"[PASS] {name}", flush=True)
        except BlockedStage as exc:
            result["status"] = "BLOCKED"
            result["reason"] = str(exc)
            print(f"[BLOCKED] {name}: {exc}", flush=True)
        except Exception as exc:  # fail closed; preserve error in the report
            result["status"] = "FAIL"
            result["reason"] = f"{type(exc).__name__}: {exc}"
            print(f"[FAIL] {name}: {result['reason']}", flush=True)
        finally:
            result["finished_at"] = self.utc_now()
            result["duration_seconds"] = round(time.monotonic() - started, 3)
            self.results.append(result)

    def command(
        self,
        name: str,
        argv: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        log_path = self.build_dir / f"{name}.log"
        actual_cwd = cwd or self.root
        print("$ " + " ".join(argv), flush=True)
        try:
            with log_path.open("w", encoding="utf-8") as log:
                proc = subprocess.run(
                    argv,
                    cwd=actual_cwd,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
        except FileNotFoundError as exc:
            raise BlockedStage(f"Required executable not found: {argv[0]}") from exc

        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-18:]:
            print(line, flush=True)
        details = {
            "command": argv,
            "working_directory": str(actual_cwd),
            "return_code": proc.returncode,
            "log": str(log_path.relative_to(self.root)),
        }
        if proc.returncode != 0:
            raise RuntimeError(
                f"Command failed with exit code {proc.returncode}; see {details['log']}"
            )
        return details

    def configuration_gate(self) -> dict[str, Any]:
        config_path = self.root / "tinytapeout-template-v2" / "src" / "config.json"
        if not config_path.is_file():
            raise RuntimeError(f"Missing configuration: {config_path}")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        expected = {
            "CTS_SINK_CLUSTERING_SIZE": 4,
            "PNR_SDC_FILE": "dir::morph_pnr.sdc",
            "SIGNOFF_SDC_FILE": "dir::morph_signoff.sdc",
        }
        mismatches = {
            key: {"expected": value, "actual": config.get(key)}
            for key, value in expected.items()
            if config.get(key) != value
        }
        if mismatches:
            raise RuntimeError("CTS4/custom-SDC config mismatch: " + json.dumps(mismatches))

        src_dir = config_path.parent
        missing = [
            name for name in ("morph_pnr.sdc", "morph_signoff.sdc")
            if not (src_dir / name).is_file()
        ]
        if missing:
            raise RuntimeError("Missing SDC source files: " + ", ".join(missing))

        production = self.root / "rtl" / "morph_engine_v2.sv"
        tt_mirror = src_dir / "morph_engine.sv"
        if not production.is_file() or not tt_mirror.is_file():
            raise RuntimeError("Production RTL or TinyTapeout RTL mirror is missing")
        if production.read_bytes() != tt_mirror.read_bytes():
            raise RuntimeError("Production RTL and TinyTapeout RTL mirror differ")

        # A broad false path on the external shared input could also hide the
        # synchronous programming-data path. Keep this guard explicit.
        sdc_text = "\n".join(
            (src_dir / name).read_text(encoding="utf-8", errors="replace")
            for name in ("morph_pnr.sdc", "morph_signoff.sdc")
        )
        broad_uio_false_paths = [
            line.strip() for line in sdc_text.splitlines()
            if "set_false_path" in line.lower() and "uio_in" in line.lower()
        ]
        if broad_uio_false_paths:
            raise RuntimeError(
                "Potentially broad false-path constraint on uio_in; this can mask programming-data timing: "
                + " | ".join(broad_uio_false_paths)
            )

        return {
            "config": str(config_path.relative_to(self.root)),
            "cts_sink_clustering_size": 4,
            "pnr_sdc": expected["PNR_SDC_FILE"],
            "signoff_sdc": expected["SIGNOFF_SDC_FILE"],
            "rtl_mirror_identical": True,
            "broad_uio_false_path_count": 0,
        }

    def contract_gate(self) -> dict[str, Any]:
        contract = self.root / "protocols" / "v2_edge_timed_release.contract.json"
        if not contract.is_file():
            raise RuntimeError(f"Missing V2 contract: {contract}")
        report = self.build_dir / "v2_edge_timed_release.contract-report.json"
        assembly = self.build_dir / "v2_edge_timed_release.generated.morph"
        details = self.command(
            "contract",
            [
                str(self.python), "compiler/morph_contract_v2.py", str(contract.relative_to(self.root)),
                "-o", str(report.relative_to(self.root)),
                "-a", str(assembly.relative_to(self.root)),
            ],
        )
        if not report.is_file():
            raise RuntimeError("Contract compiler returned success but emitted no report")
        payload = json.loads(report.read_text(encoding="utf-8"))
        if payload.get("status") != "PASS":
            raise RuntimeError("V2 temporal contract report is not PASS")
        details.update({"report": str(report.relative_to(self.root)), "contract_status": payload.get("status")})
        return details

    def python_regression(self) -> dict[str, Any]:
        if not (self.root / "sim").is_dir():
            raise RuntimeError("sim/ directory is missing")
        return self.command("python-regression", [str(self.python), "-m", "pytest", "-q", "sim"])

    def cocotb_regression(self) -> dict[str, Any]:
        test_dir = self.root / "tinytapeout-template-v2" / "test"
        if not (test_dir / "Makefile").is_file():
            raise RuntimeError("TinyTapeout test/Makefile is missing")
        for executable in ("make", "iverilog", "cocotb-config"):
            if shutil.which(executable) is None:
                raise BlockedStage(f"TinyTapeout simulation dependency missing: {executable}")

        clean = self.command("cocotb-clean", ["make", "clean"], cwd=test_dir)
        run = self.command("cocotb-rtl", ["make"], cwd=test_dir)
        results_xml = test_dir / "results.xml"
        if not results_xml.is_file():
            raise RuntimeError("Cocotb make completed but results.xml was not produced")
        root = ET.parse(results_xml).getroot()
        cases = list(root.iter("testcase"))
        failures = sum(len(case.findall("failure")) + len(case.findall("error")) for case in cases)
        if not cases:
            raise RuntimeError("Cocotb produced zero test cases")
        if failures:
            raise RuntimeError(f"Cocotb XML reports {failures} failing/error test cases")
        return {
            "clean_command": clean,
            "simulation_command": run,
            "test_cases": len(cases),
            "failures": failures,
            "results_xml": str(results_xml.relative_to(self.root)),
        }

    def yosys_and_cdc(self) -> dict[str, Any]:
        if shutil.which("yosys") is None:
            raise BlockedStage("Yosys is not installed or not on PATH")
        rtl = self.root / "rtl" / "morph_engine_v2.sv"
        mirror = self.root / "tinytapeout-template-v2" / "src" / "morph_engine.sv"
        if not rtl.is_file() or not mirror.is_file():
            raise RuntimeError("Production RTL or TinyTapeout RTL mirror is missing")
        source = rtl.read_text(encoding="utf-8")
        patterns = {
            "stage1_attribute": r'\(\*\s*ASYNC_REG\s*=\s*"TRUE"\s*\*\)\s*logic\s+\[7:0\]\s+pin_sync_1\s*;',
            "stage2_attribute": r'\(\*\s*ASYNC_REG\s*=\s*"TRUE"\s*\*\)\s*logic\s+\[7:0\]\s+pin_sync_2\s*;',
            "stage1_samples_raw_pin": r'\bpin_sync_1\s*<=\s*pin_in\s*;',
            "stage2_samples_stage1": r'\bpin_sync_2\s*<=\s*pin_sync_1\s*;',
            "sample_uses_stage2": r'sample_reg\s*<=\s*pin_sync_2\s*\[',
            "edge_wait_uses_stage2": r'pin_sync_2\s*\[ir\[10:8\]\]',
            "previous_sample_uses_stage2": r'pin_prev\s*<=\s*pin_sync_2\s*;',
        }
        failed = [name for name, pattern in patterns.items() if not re.search(pattern, source)]
        if failed:
            raise RuntimeError("RTL CDC source checks failed: " + ", ".join(failed))

        # Raw asynchronous pin_in must feed only synchronizer stage 1 in this
        # engine. The separate program_byte bus remains synchronous.
        pin_in_lines = [
            line.strip() for line in source.splitlines()
            if re.search(r"\bpin_in\b", line)
            and not re.search(r"input\s+logic", line)
        ]
        if pin_in_lines != ["pin_sync_1 <= pin_in;"]:
            raise RuntimeError("Unexpected direct pin_in use outside synchronizer stage 1: " + repr(pin_in_lines))

        netlist = self.build_dir / "morph_engine_v2.precdc.json"
        yosys_script = (
            f"read_verilog -sv {rtl}; "
            "hierarchy -check -top morph_engine_v2; "
            "proc; opt; "
            f"write_json {netlist}; "
            "synth -top morph_engine_v2 -flatten; "
            "check -assert; stat"
        )
        details = self.command("yosys-synthesis-cdc", ["yosys", "-p", yosys_script])
        if not netlist.is_file():
            raise RuntimeError("Yosys completed but pre-CDC netlist JSON was not emitted")

        design = json.loads(netlist.read_text(encoding="utf-8"))
        module = design.get("modules", {}).get("morph_engine_v2")
        if module is None:
            raise RuntimeError("Yosys JSON does not contain morph_engine_v2")
        ports = module.get("ports", {})
        nets = module.get("netnames", {})
        cells = module.get("cells", {})
        try:
            input_bits = ports["pin_in"]["bits"]
            stage1_bits = nets["pin_sync_1"]["bits"]
            stage2_bits = nets["pin_sync_2"]["bits"]
        except KeyError as exc:
            raise RuntimeError(f"Yosys JSON missing expected synchronizer net/port: {exc}") from exc
        if not (len(input_bits) == len(stage1_bits) == len(stage2_bits) == 8):
            raise RuntimeError("Yosys synchronizer or input bus is not exactly 8 bits")

        q_to_d: dict[Any, Any] = {}
        for cell in cells.values():
            conns = cell.get("connections", {})
            directions = cell.get("port_directions", {})
            if not {"D", "Q", "CLK"}.issubset(conns):
                continue
            if directions and (directions.get("D") != "input" or directions.get("Q") != "output"):
                continue
            q_bits, d_bits = conns["Q"], conns["D"]
            if len(q_bits) != len(d_bits):
                continue
            for q_bit, d_bit in zip(q_bits, d_bits):
                q_to_d[q_bit] = d_bit

        def check_stage(stage_bits: list[Any], expected_d: list[Any], label: str) -> None:
            missing = [bit for bit in stage_bits if bit not in q_to_d]
            if missing:
                raise RuntimeError(f"Yosys netlist has no D/Q flop mapping for {label}: {missing}")
            actual_d = [q_to_d[bit] for bit in stage_bits]
            if actual_d != expected_d:
                raise RuntimeError(f"Yosys D-input mapping for {label} is not the expected source bus")

        check_stage(stage1_bits, input_bits, "pin_sync_1")
        check_stage(stage2_bits, stage1_bits, "pin_sync_2")
        details.update({
            "netlist": str(netlist.relative_to(self.root)),
            "synchronizer_width": 8,
            "stage1_d_source": "pin_in",
            "stage2_d_source": "pin_sync_1",
            "rtl_attribute": "ASYNC_REG=TRUE on both stages",
            "raw_pin_in_consumers": pin_in_lines,
            "structural_cdc_status": "PASS",
        })
        return details

    def download_gds_artifact(self) -> Path | None:
        if not self.args.github_run_id:
            return None
        if shutil.which("gh") is None:
            raise BlockedStage("GitHub CLI (gh) is required for --github-run-id")

        metadata = self.command(
            "github-run-metadata",
            [
                "gh", "run", "view", str(self.args.github_run_id),
                "--json", "status,conclusion,jobs,url,headSha",
            ],
        )
        metadata_path = self.build_dir / "github-run-metadata.log"
        try:
            run = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("gh run view did not return valid JSON") from exc
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            raise RuntimeError(
                "GitHub run is not fully successful: "
                f"status={run.get('status')!r}, conclusion={run.get('conclusion')!r}"
            )

        jobs = run.get("jobs") or []
        required_job_aliases = {
            "rtl-regression": {"rtl-regression"},
            "tinytapeout-rtl": {"tinytapeout-rtl"},
            "gds": {"gds"},
            "precheck": {"precheck"},
            "gate-level-test": {"gate-level-test"},
            # The workflow assigns this job a human-readable display name.
            "physical-signoff": {"physical-signoff", "Final post-route physical gate"},
        }
        missing: list[str] = []
        failed: dict[str, Any] = {}
        for logical_name, aliases in required_job_aliases.items():
            matches = [job for job in jobs if job.get("name") in aliases]
            if not matches:
                missing.append(logical_name)
                continue
            selected = matches[-1]
            if selected.get("status") != "completed" or selected.get("conclusion") != "success":
                failed[logical_name] = {
                    "reported_name": selected.get("name"),
                    "status": selected.get("status"),
                    "conclusion": selected.get("conclusion"),
                }
        if missing or failed:
            raise RuntimeError(
                "GitHub run is missing required successful qualification jobs: "
                + json.dumps({"missing": missing, "not_successful": failed})
            )

        destination = self.build_dir / "gds-artifact"
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
        self.command(
            "download-gds-artifact",
            [
                "gh", "run", "download", str(self.args.github_run_id),
                "--name", "GDS_logs", "--dir", str(destination),
            ],
        )
        return destination

    @staticmethod
    def find_artifact_root(reports_dir: Path) -> Path | None:
        candidate = reports_dir.resolve()
        for parent in [candidate, *candidate.parents]:
            if (parent / "src" / "config_merged.json").is_file():
                return parent
        return None

    def physical_gate(self) -> dict[str, Any]:
        downloaded_root = self.download_gds_artifact()
        reports_arg = self.args.reports_dir
        if reports_arg:
            reports_dir = Path(reports_arg).expanduser().resolve()
        elif downloaded_root:
            reports_dir = downloaded_root / "runs" / "wokwi" / "55-openroad-stapostpnr"
        else:
            reports_dir = self.root / "runs" / "wokwi" / "55-openroad-stapostpnr"

        if not reports_dir.is_dir():
            raise BlockedStage(
                f"Post-route reports not found at {reports_dir}. Supply --github-run-id <completed GDS run> "
                "or --reports-dir <.../runs/wokwi/55-openroad-stapostpnr>."
            )

        artifact_root = self.find_artifact_root(reports_dir)
        if artifact_root is None:
            raise BlockedStage(
                "Could not locate src/config_merged.json above the reports directory; "
                "use the complete extracted GDS_logs artifact, not only the STA subfolder."
            )

        merged_path = artifact_root / "src" / "config_merged.json"
        merged = json.loads(merged_path.read_text(encoding="utf-8"))
        expected = {
            "CTS_SINK_CLUSTERING_SIZE": 4,
            "PNR_SDC_FILE": "dir::morph_pnr.sdc",
            "SIGNOFF_SDC_FILE": "dir::morph_signoff.sdc",
        }
        mismatches = {
            key: {"expected": value, "actual": merged.get(key)}
            for key, value in expected.items()
            if merged.get(key) != value
        }
        if mismatches:
            raise RuntimeError("Generated GDS merged config does not prove CTS4/custom SDC: " + json.dumps(mismatches))

        pnr_cfg = artifact_root / "runs" / "wokwi" / "13-openroad-floorplan" / "config.json"
        sta_cfg = artifact_root / "runs" / "wokwi" / "55-openroad-stapostpnr" / "config.json"
        for path in (pnr_cfg, sta_cfg):
            if not path.is_file():
                raise RuntimeError(f"Missing resolved LibreLane step configuration: {path}")
        pnr_json = json.loads(pnr_cfg.read_text(encoding="utf-8"))
        sta_json = json.loads(sta_cfg.read_text(encoding="utf-8"))
        pnr_sdc = str(pnr_json.get("PNR_SDC_FILE") or "").replace("\\", "/")
        signoff_sdc = str(sta_json.get("SIGNOFF_SDC_FILE") or "").replace("\\", "/")
        if not pnr_sdc.endswith("morph_pnr.sdc"):
            raise RuntimeError(f"Resolved PnR step did not load morph_pnr.sdc: {pnr_sdc!r}")
        if not signoff_sdc.endswith("morph_signoff.sdc"):
            raise RuntimeError(f"Resolved post-route STA step did not load morph_signoff.sdc: {signoff_sdc!r}")

        for name in ("morph_pnr.sdc", "morph_signoff.sdc"):
            if not (artifact_root / "src" / name).is_file():
                raise RuntimeError(f"GDS artifact is missing src/{name}")

        checker = self.root / "scripts" / "check_physical_signoff.py"
        if not checker.is_file():
            raise BlockedStage("scripts/check_physical_signoff.py is missing from this checkout")
        physical_report = self.build_dir / "physical-signoff-gate.json"
        command = self.command(
            "physical-signoff",
            [
                str(self.python), str(checker),
                "--reports-dir", str(reports_dir),
                "--report-json", str(physical_report),
            ],
        )
        if not physical_report.is_file():
            raise RuntimeError("Physical signoff checker completed without writing its JSON report")
        report_json = json.loads(physical_report.read_text(encoding="utf-8"))
        return {
            "artifact_root": str(artifact_root),
            "reports_dir": str(reports_dir),
            "cts_sink_clustering_size": merged.get("CTS_SINK_CLUSTERING_SIZE"),
            "merged_pnr_sdc": merged.get("PNR_SDC_FILE"),
            "resolved_pnr_sdc": pnr_sdc,
            "merged_signoff_sdc": merged.get("SIGNOFF_SDC_FILE"),
            "resolved_signoff_sdc": signoff_sdc,
            "signoff_checker": command,
            "signoff_report": str(physical_report.relative_to(self.root)),
            "signoff_report_status": report_json.get("status", "checker-exit-0"),
        }

    def write_summary(self) -> dict[str, Any]:
        statuses = [item["status"] for item in self.results]
        if "FAIL" in statuses:
            overall = "FAIL"
        elif "BLOCKED" in statuses:
            overall = "INCOMPLETE"
        else:
            overall = "PASS"
        report = {
            "schema_version": 1,
            "project": "MORPH",
            "qualification_profile": "V2 full engineering qualification / CTS4",
            "overall_status": overall,
            "started_at": self.started,
            "finished_at": self.utc_now(),
            "repository_root": str(self.root),
            "git_commit": self.git_commit(),
            "stages": self.results,
            "coverage_notes": [
                "The physical implementation itself is generated by the TinyTapeout IHP/LibreLane GitHub Actions job; this runner consumes its GDS_logs artifact.",
                "CDC checks verify the two-stage synchronizer RTL and its Yosys D/Q topology. They do not model analog metastability or calculate MTBF.",
                "The physical signoff checker evaluates the reports it supports; this runner does not claim LVS or board-level electrical qualification unless separately reported by the flow.",
            ],
        }
        output = Path(self.args.output).expanduser()
        if not output.is_absolute():
            output = self.root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nQualification report: {output}")
        print("\nFINAL QUALIFICATION STATUS")
        for item in self.results:
            marker = {"PASS": "PASS", "FAIL": "FAIL", "BLOCKED": "BLOCKED"}[item["status"]]
            print(f"  [{marker:7}] {item['name']}")
        print(f"\nOVERALL: {overall}")
        return report

    def git_commit(self) -> str | None:
        if shutil.which("git") is None:
            return None
        try:
            p = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=self.root,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, check=False,
            )
            return p.stdout.strip() if p.returncode == 0 else None
        except OSError:
            return None


def locate_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "rtl" / "morph_engine_v2.sv").is_file() and (candidate / "sim").is_dir():
            return candidate
    raise SystemExit("Could not locate MORPH repository root (expected rtl/morph_engine_v2.sv and sim/)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--github-run-id", type=int,
        help="Download the GDS_logs artifact from this completed GitHub Actions run (requires gh auth).",
    )
    parser.add_argument(
        "--reports-dir", type=Path,
        help="Existing runs/wokwi/55-openroad-stapostpnr directory from an extracted GDS_logs artifact.",
    )
    parser.add_argument(
        "--output", default="build/qualification/qualification-report.json",
        help="Unified JSON report path (default: build/qualification/qualification-report.json).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = locate_root(Path.cwd().resolve())
    runner = Qualification(root, args)

    runner.stage("CTS4 and custom-SDC source configuration", runner.configuration_gate)
    runner.stage("V2 temporal contract compilation and verification", runner.contract_gate)
    runner.stage("Python model / assembler / RTL differential regression", runner.python_regression)
    runner.stage("TinyTapeout RTL Cocotb regression", runner.cocotb_regression)
    runner.stage("Yosys synthesis and structural CDC qualification", runner.yosys_and_cdc)
    runner.stage("Generated CTS4 / SDC verification and physical signoff", runner.physical_gate)

    report = runner.write_summary()
    if report["overall_status"] == "PASS":
        return 0
    if report["overall_status"] == "FAIL":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
