import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path.home() / "MORPH"
TRACE_REL = Path("traceforge/rtl_run/protocol_traces")
CONTRACT_REL = Path("traceforge/contracts")
REPORT_REL = Path("traceforge/reports")
CHECKER_REL = Path("traceforge/rtl_run/check_traceforge_protocol_traces.py")
RESULTS_REL = REPORT_REL / "traceforge_protocol_trace_results.xml"
REPORT_PATH = ROOT / REPORT_REL / "traceforge_negative_controls_v0.1.json"
MARKDOWN_PATH = ROOT / REPORT_REL / "traceforge_negative_controls_v0.1.md"

REQUIRED_FILES = [
    CHECKER_REL,
    TRACE_REL / "spi_mode0_a5_trace.json",
    TRACE_REL / "i2c_address_probe_ack_trace.json",
    TRACE_REL / "i2c_nack_trace.json",
    CONTRACT_REL / "spi_trace_contract_v0.1.json",
    CONTRACT_REL / "i2c_trace_contract_v0.1.json",
    RESULTS_REL,
    Path("rtl/morph_engine_v2.sv"),
    Path("tinytapeout-template-v2/src/morph_engine.sv"),
]

for rel in REQUIRED_FILES:
    if not (ROOT / rel).is_file():
        raise SystemExit(f"Required artifact missing: {ROOT / rel}")

rtl_hash = hashlib.sha256((ROOT / "rtl/morph_engine_v2.sv").read_bytes()).hexdigest()


def copy_layout(destination: Path) -> None:
    for rel in REQUIRED_FILES:
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)


def load_json(path: Path):
    return json.loads(path.read_text())


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def flip_first_spi_mosi_bit(case_root: Path) -> None:
    path = case_root / TRACE_REL / "spi_mode0_a5_trace.json"
    trace = load_json(path)
    last_clk = None
    flipped = False
    for sample in trace["samples"]:
        oe = int(sample["uio_oe"])
        out = int(sample["uio_out"])
        if (oe & 0x07) != 0x07:
            continue
        clk = (out >> 2) & 1
        if last_clk == 0 and clk == 1:
            sample["uio_out"] = out ^ 0x02
            flipped = True
            break
        last_clk = clk
    if not flipped:
        raise RuntimeError("Could not find the first SPI rising edge to corrupt")
    save_json(path, trace)


def remove_simulated_i2c_ack(case_root: Path) -> None:
    path = case_root / TRACE_REL / "i2c_address_probe_ack_trace.json"
    trace = load_json(path)
    changed = 0
    for sample in trace["samples"]:
        if int(sample.get("rising_count_fixture", -1)) != 9 or not bool(sample.get("slave_sda_low", False)):
            continue
        oe = int(sample["uio_oe"])
        out = int(sample["uio_out"])
        master_sda_low = bool((oe & 0x02) and not (out & 0x02))
        master_scl_low = bool((oe & 0x04) and not (out & 0x04))
        sample["slave_sda_low"] = False
        sample["bus_scl"] = 0 if master_scl_low else 1
        sample["bus_sda"] = 0 if master_sda_low else 1
        bus_input = 0xFF
        if sample["bus_scl"] == 0:
            bus_input &= ~0x04
        if sample["bus_sda"] == 0:
            bus_input &= ~0x02
        sample["uio_in_next"] = bus_input
        changed += 1
    if not changed:
        raise RuntimeError("Could not find the simulated I2C ACK interval to corrupt")
    save_json(path, trace)


def force_nack_lines_not_released(case_root: Path) -> None:
    path = case_root / TRACE_REL / "i2c_nack_trace.json"
    trace = load_json(path)
    changed = 0
    for sample in trace["samples"]:
        oe = int(sample["uio_oe"])
        out = int(sample["uio_out"])
        if (oe & 0x80) and (out & 0x80):
            sample["uio_oe"] = oe | 0x06
            changed += 1
    if not changed:
        raise RuntimeError("Could not find the NACK fault interval to corrupt")
    save_json(path, trace)


def run_checker(case_root: Path):
    checker = case_root / CHECKER_REL
    env = os.environ.copy()
    env["MORPH_RTL_SHA256_BEFORE"] = rtl_hash
    env["MORPH_RTL_SHA256_AFTER"] = rtl_hash
    result = subprocess.run(
        [sys.executable, str(checker)],
        cwd=case_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    report_path = case_root / REPORT_REL / "protocol_trace_contract_validation_v0.1.json"
    report = load_json(report_path) if report_path.is_file() else None
    return result, report


scenarios = []
with tempfile.TemporaryDirectory(prefix="morph-traceforge-negative-") as temp_dir:
    temp_root = Path(temp_dir)
    base_root = temp_root / "baseline"
    copy_layout(base_root)

    baseline_proc, baseline_report = run_checker(base_root)
    baseline_pass = baseline_proc.returncode == 0 and baseline_report is not None and baseline_report.get("status") == "PASS"
    scenarios.append({
        "scenario": "clean_baseline",
        "expected": "PASS",
        "actual": "PASS" if baseline_pass else "FAIL",
        "checks_passed": None if baseline_report is None else baseline_report.get("checks_passed"),
        "checks_failed": None if baseline_report is None else baseline_report.get("checks_failed"),
        "detected_failures": [],
        "output_tail": baseline_proc.stdout.splitlines()[-8:],
        "test_passed": baseline_pass,
    })

    mutations = [
        ("flip_spi_mosi_bit", flip_first_spi_mosi_bit, {"SPI MOSI sequence"}),
        ("remove_i2c_slave_ack", remove_simulated_i2c_ack, {"I2C slave ACK level"}),
        ("break_i2c_nack_line_release", force_nack_lines_not_released, {"I2C NACK fault is signaled", "I2C NACK releases SDA/SCL"}),
    ]

    for name, mutate, expected_failures in mutations:
        case_root = temp_root / name
        shutil.copytree(base_root, case_root)
        mutate(case_root)
        proc, report = run_checker(case_root)
        failed_checks = [] if report is None else [c["name"] for c in report.get("checks", []) if c.get("status") == "FAIL"]
        detected = sorted(set(failed_checks) & expected_failures)
        passed = proc.returncode != 0 and bool(detected)
        scenarios.append({
            "scenario": name,
            "expected": "FAIL with targeted contract violation",
            "actual": "REJECTED" if passed else "UNEXPECTED RESULT",
            "checks_passed": None if report is None else report.get("checks_passed"),
            "checks_failed": None if report is None else report.get("checks_failed"),
            "detected_failures": failed_checks,
            "targeted_failure_detected": detected,
            "output_tail": proc.stdout.splitlines()[-8:],
            "test_passed": passed,
        })

all_passed = all(s["test_passed"] for s in scenarios)
result_data = {
    "schema": "morph.traceforge-negative-controls.v0.1",
    "status": "PASS" if all_passed else "FAIL",
    "baseline_rtl_sha256": rtl_hash,
    "production_rtl_modified": False,
    "source_traces_modified": False,
    "temporary_workspace_only": True,
    "scenario_count": len(scenarios),
    "scenarios_passed": sum(bool(s["test_passed"]) for s in scenarios),
    "scenarios_failed": sum(not bool(s["test_passed"]) for s in scenarios),
    "scenarios": scenarios,
}
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
save_json(REPORT_PATH, result_data)
md_lines = [
    "# TRACEFORGE Protocol Checker Negative Controls v0.1",
    "",
    f"**Status:** {result_data['status']}",
    f"**Scenarios:** {result_data['scenarios_passed']}/{result_data['scenario_count']} passed",
    "",
    "The clean baseline must pass, while deliberately corrupted temporary trace copies must be rejected by their expected protocol checks.",
    "",
    "| Scenario | Expected | Result | Targeted failure(s) detected |",
    "|---|---|---|---|",
]
for scenario in scenarios:
    targeted = ", ".join(scenario.get("targeted_failure_detected", [])) or "—"
    md_lines.append(f"| {scenario['scenario']} | {scenario['expected']} | {scenario['actual']} | {targeted} |")
md_lines += [
    "",
    f"- Production RTL SHA-256: `{rtl_hash}`",
    "- The three source trace JSON files were copied to a temporary workspace before mutation.",
    "- No production RTL, checked-in trace, contract, or original regression result was changed by these negative controls.",
    "- The I²C ACK is simulated testbench stimulus, not a real external slave measurement.",
    "",
]
MARKDOWN_PATH.write_text("\n".join(md_lines))

print(json.dumps({
    "status": result_data["status"],
    "scenarios_passed": result_data["scenarios_passed"],
    "scenarios_failed": result_data["scenarios_failed"],
    "json_report": str(REPORT_PATH),
    "markdown_report": str(MARKDOWN_PATH),
}, indent=2))
for scenario in scenarios:
    print(f"{'PASS' if scenario['test_passed'] else 'FAIL'}: {scenario['scenario']} -> {scenario['actual']}")
    if scenario.get("targeted_failure_detected"):
        print("  detected: " + ", ".join(scenario["targeted_failure_detected"]))
if not all_passed:
    for scenario in scenarios:
        if not scenario["test_passed"]:
            print(f"\n--- {scenario['scenario']} output ---")
            print("\n".join(scenario.get("output_tail", [])))
    raise SystemExit(1)
