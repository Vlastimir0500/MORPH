from __future__ import annotations
import collections
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / "MORPH"
WORK = ROOT / "traceforge" / "rtl_run"
REPORTS = ROOT / "traceforge" / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WORK))

import traceforge_uart_rtl as uart
from sim.morph_isa_model_v2 import MorphISAModelV2

NOMINAL = int(uart.BIT_PERIOD)
IDLE = int(uart.IDLE_CYCLES)
TAIL = int(uart.TAIL_CYCLES)
LOW_RUN_NOMINAL = 9 * NOMINAL
DELTAS = [-218, -217, -216, -215, -214, -213, 0]
PAYLOAD = 0x00
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_{os.getpid()}"
RUN_DIR = WORK / f"uart_boundary_diagnostic_v0_1_{RUN_ID}"
RUN_DIR.mkdir(parents=True, exist_ok=False)
BUILD_DIR = RUN_DIR / "obj_dir"
BUILD_DIR.mkdir()
PROGRAM_FILE = RUN_DIR / "morph_v2_program.hex"
VECTOR_FILE = RUN_DIR / "morph_v2_vectors.hex"
ISOLATED_TB = RUN_DIR / "morph_engine_v2_traceforge_tb.sv"
CSV_PATH = RUN_DIR / "boundary_trace_cycles.csv"

RTL = ROOT / "rtl" / "morph_engine_v2.sv"
SOURCE_TB = WORK / "morph_engine_v2_traceforge_tb.sv"
FIRMWARE = ROOT / "protocols" / "v2_uart_rx_a6.hex"
MIN_REPORT_PATH = REPORTS / "uart_rx_minimized_counterexample.json"
MIN_VECTOR_PATH = REPORTS / "uart_rx_minimized_counterexample_vectors.hex"
if not SOURCE_TB.is_file() or not MIN_REPORT_PATH.is_file() or not MIN_VECTOR_PATH.is_file():
    raise FileNotFoundError("Missing UART differential bench or minimized counterexample evidence")
MIN_REPORT = json.loads(MIN_REPORT_PATH.read_text())
BASE_OFFSETS = list(MIN_REPORT["minimized"]["offsets"])
KNOWN_DELTA = sum(BASE_OFFSETS[:9])
RTL_HASH_BEFORE = hashlib.sha256(RTL.read_bytes()).hexdigest()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_testbench_path(source: str, basename: str, target: Path) -> tuple[str, int]:
    pattern = re.compile(r'(?P<quote>["\'])(?:[^"\']*[\\/])?' + re.escape(basename) + r'(?P=quote)')
    updated, count = pattern.subn(lambda match: match.group("quote") + str(target) + match.group("quote"), source)
    if count < 1:
        raise RuntimeError(f"Could not replace testbench filename {basename}")
    return updated, count


def make_low_run_vector(delta: int) -> list[int]:
    low_cycles = LOW_RUN_NOMINAL + delta
    if low_cycles <= 0:
        raise ValueError("Non-positive low-run duration")
    return [1] * IDLE + [0] * low_cycles + [1] * (NOMINAL + TAIL)


PROGRAM = [int(line.strip(), 16) for line in FIRMWARE.read_text().splitlines() if line.strip()]
if len(PROGRAM) != 18:
    raise RuntimeError(f"Expected 18 UART RX instructions, found {len(PROGRAM)}")
if KNOWN_DELTA != -216:
    raise RuntimeError(f"Expected minimized aggregate delta -216, found {KNOWN_DELTA}")
SOURCE_TEXT = SOURCE_TB.read_text()
SOURCE_TEXT, PROGRAM_REPLACEMENTS = replace_testbench_path(SOURCE_TEXT, "morph_v2_program.hex", PROGRAM_FILE)
SOURCE_TEXT, VECTOR_REPLACEMENTS = replace_testbench_path(SOURCE_TEXT, "morph_v2_vectors.hex", VECTOR_FILE)
ISOLATED_TB.write_text(SOURCE_TEXT)

VERILATOR = shutil.which("verilator")
if not VERILATOR:
    raise RuntimeError("Verilator not found after loading OSS CAD Suite")
BUILD = subprocess.run(
    [VERILATOR, "--binary", "--timing", "-Wno-fatal", "--top-module", "morph_engine_v2_diff_tb", "--Mdir", str(BUILD_DIR), str(RTL), str(ISOLATED_TB)],
    cwd=ROOT, capture_output=True, text=True, timeout=240,
)
(RUN_DIR / "verilator_build.stdout.log").write_text(BUILD.stdout)
(RUN_DIR / "verilator_build.stderr.log").write_text(BUILD.stderr)
if BUILD.returncode:
    raise RuntimeError("Isolated Verilator build failed; inspect run-directory build logs")
EXECUTABLE = BUILD_DIR / "Vmorph_engine_v2_diff_tb"
if not EXECUTABLE.is_file():
    raise RuntimeError("Compiled UART diagnostic executable is missing")

EXPECTED_SHIFT = int(MIN_REPORT["minimized"]["expected_shift_register"], 16)
SAMPLE_PCS = {2, 6, 11}
NEARBY_PCS = {6, 7, 10, 11, 12, 13}
all_cases = []
all_csv_rows = []


def evaluate(delta: int) -> dict:
    low_cycles = LOW_RUN_NOMINAL + delta
    pins = make_low_run_vector(delta)
    PROGRAM_FILE.write_text("".join(f"{word:04x}\n" for word in PROGRAM + [0] * (64 - len(PROGRAM))))
    VECTOR_FILE.write_text("".join(f"{pin:02x}\n" for pin in pins))

    model = MorphISAModelV2()
    model.load_program(PROGRAM)
    expected = [uart.expected_snapshot(model.step(rst_n=False, pin_in=0))]
    expected.extend(uart.expected_snapshot(model.step(pin_in=pin)) for pin in pins)
    sim = subprocess.run([str(EXECUTABLE), f"+N={len(pins)}"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    if sim.returncode:
        raise RuntimeError(f"Simulation failed at delta {delta}:\n{sim.stdout[-2500:]}\n{sim.stderr[-2500:]}")

    actual = uart.parse_trace(sim.stdout)
    mismatch = None
    if len(actual) != len(expected):
        mismatch = {"kind": "trace_length", "rtl_cycles": len(actual), "model_cycles": len(expected)}
    else:
        for index, (got, want) in enumerate(zip(actual, expected)):
            if got != want:
                mismatch = {"kind": "cycle_mismatch", "trace_index": index, "rtl": list(got), "model": list(want)}
                break
    if not actual:
        raise RuntimeError("Simulation produced an empty trace")

    final = actual[-1]
    error_flag = bool((final[3] & final[4]) & 0x80)
    core_fault = bool(final[9])
    observed_shift = final[6]
    if mismatch:
        classification = "rtl_model_mismatch"
    elif error_flag:
        classification = "error_flagged"
    elif core_fault:
        classification = "core_fault"
    elif observed_shift != EXPECTED_SHIFT:
        classification = "silent_misdecode"
    else:
        classification = "correct_decode"

    edge_vector_index = IDLE + low_cycles
    edge_trace_index = edge_vector_index + 1
    events = []
    previous = None
    for index, row in enumerate(actual):
        vector_index = index - 1 if index > 0 else None
        input_value = pins[vector_index] if vector_index is not None and vector_index < len(pins) else None
        edge_distance = index - edge_trace_index
        tags = []
        if -6 <= edge_distance <= 6:
            tags.append("near_input_rising_edge")
        if previous is not None:
            if row[1] != previous[1] and row[1] in NEARBY_PCS:
                tags.append("pc_transition_of_interest")
            if row[1] in SAMPLE_PCS and row[0] != previous[0]:
                tags.append("sample_instruction_state_transition")
            if row[5] != previous[5]:
                tags.append("sample_register_changed")
            if row[6] != previous[6]:
                tags.append("shift_register_changed")
        if tags:
            events.append({
                "trace_index": index,
                "input_vector_index": vector_index,
                "distance_from_input_rising_edge_cycles": edge_distance,
                "input_pin0": input_value,
                "state": row[0],
                "pc": row[1],
                "instruction_hex": f"0x{row[2]:04X}",
                "pin_out_hex": f"0x{row[3]:02X}",
                "pin_oe_hex": f"0x{row[4]:02X}",
                "sample_reg": row[5],
                "shift_reg_hex": f"0x{row[6]:02X}",
                "wait_count": row[7],
                "timed_out": bool(row[8]),
                "fault": bool(row[9]),
                "event_tags": tags,
            })
        all_csv_rows.append({
            "delta_cycles": delta,
            "low_run_duration_cycles": low_cycles,
            "trace_index": index,
            "input_vector_index": vector_index,
            "input_pin0": input_value,
            "distance_from_input_rising_edge_cycles": edge_distance,
            "state": row[0],
            "pc": row[1],
            "instruction_hex": f"0x{row[2]:04X}",
            "pin_out_hex": f"0x{row[3]:02X}",
            "pin_oe_hex": f"0x{row[4]:02X}",
            "sample_reg": row[5],
            "shift_reg_hex": f"0x{row[6]:02X}",
            "wait_count": row[7],
            "timed_out": bool(row[8]),
            "fault": bool(row[9]),
        })
        previous = row

    result = {
        "delta_cycles": delta,
        "low_run_duration_cycles": low_cycles,
        "expected_shift_register": f"0x{EXPECTED_SHIFT:02X}",
        "observed_shift_register": f"0x{observed_shift:02X}",
        "error_flag_pin7": error_flag,
        "core_fault": core_fault,
        "classification": classification,
        "rtl_reference_model_match": mismatch is None,
        "first_mismatch": mismatch,
        "input_rising_edge_vector_index": edge_vector_index,
        "input_rising_edge_trace_index": edge_trace_index,
        "trace_rows": len(actual),
        "event_count": len(events),
        "events": events,
    }
    all_cases.append(result)
    print(f"delta {delta:+d}: low_run={low_cycles}, classification={classification}, RTL/model_match={mismatch is None}, edge_trace_index={edge_trace_index}", flush=True)
    return result


print("===== UART BOUNDARY CYCLE DIAGNOSTIC v0.1 =====")
print(f"Output directory: {RUN_DIR}")
print(f"Production RTL SHA256 before run: {RTL_HASH_BEFORE}")
print(f"Nominal low run: {LOW_RUN_NOMINAL} cycles; tested deltas: {DELTAS}")
print("Capture includes per-cycle PC, instruction, sample/shift registers, input edge alignment, and RTL/model comparison.")

for delta in DELTAS:
    evaluate(delta)

saved_vector = [int(line.strip(), 16) for line in MIN_VECTOR_PATH.read_text().splitlines() if line.strip()]
reconstructed_known = make_low_run_vector(KNOWN_DELTA)
known_vector_exact_match = reconstructed_known == saved_vector
known = next(item for item in all_cases if item["delta_cycles"] == -216)
previous_cycle = next(item for item in all_cases if item["delta_cycles"] == -217)
next_cycle = next(item for item in all_cases if item["delta_cycles"] == -215)
nominal = next(item for item in all_cases if item["delta_cycles"] == 0)
RTL_HASH_AFTER = digest(RTL)
all_match = all(item["rtl_reference_model_match"] for item in all_cases)
summary = {
    "status": "PASS" if all_match and known_vector_exact_match and nominal["classification"] == "correct_decode" and known["classification"] == "silent_misdecode" and previous_cycle["classification"] == "silent_misdecode" and next_cycle["classification"] == "correct_decode" and RTL_HASH_AFTER == RTL_HASH_BEFORE else "FAIL",
    "cases": len(all_cases),
    "classification_counts": dict(sorted(collections.Counter(item["classification"] for item in all_cases).items())),
    "rtl_reference_model_mismatches": sum(not item["rtl_reference_model_match"] for item in all_cases),
    "low_run_delta_minus_217": previous_cycle["classification"],
    "low_run_delta_minus_216": known["classification"],
    "low_run_delta_minus_215": next_cycle["classification"],
    "nominal_baseline": nominal["classification"],
    "known_counterexample_vector_exact_match": known_vector_exact_match,
    "production_rtl_unchanged": RTL_HASH_AFTER == RTL_HASH_BEFORE,
}

with CSV_PATH.open("w", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=list(all_csv_rows[0].keys()))
    writer.writeheader()
    writer.writerows(all_csv_rows)

report = {
    "tool": "TRACEFORGE",
    "version": "0.1.0",
    "experiment": "Cycle-level diagnosis around the UART aggregate low-run boundary",
    "scope": "Finite simulation diagnostic for the current UART RX firmware and RTL. Not a universal UART timing specification.",
    "summary": summary,
    "parameters": {
        "nominal_symbol_duration_cycles": NOMINAL,
        "nominal_low_run_cycles": LOW_RUN_NOMINAL,
        "tested_deltas_cycles": DELTAS,
        "saved_counterexample_aggregate_delta_cycles": KNOWN_DELTA,
        "sample_instruction_pcs": sorted(SAMPLE_PCS),
    },
    "source_hashes": {
        "production_rtl_sha256_before": RTL_HASH_BEFORE,
        "production_rtl_sha256_after": RTL_HASH_AFTER,
        "uart_rx_firmware_sha256": digest(FIRMWARE),
        "source_testbench_sha256": digest(SOURCE_TB),
        "isolated_testbench_sha256": digest(ISOLATED_TB),
        "saved_counterexample_report_sha256": digest(MIN_REPORT_PATH),
        "saved_counterexample_vector_sha256": digest(MIN_VECTOR_PATH),
    },
    "cycle_trace_csv": str(CSV_PATH),
    "cases": all_cases,
}
json_path = REPORTS / f"uart_boundary_diagnostic_v0_1_{RUN_ID}.json"
md_path = REPORTS / f"uart_boundary_diagnostic_v0_1_{RUN_ID}.md"
json_path.write_text(json.dumps(report, indent=2) + "\n")

lines = [
    "# TRACEFORGE â€” UART Boundary Cycle Diagnostic v0.1",
    "",
    f"- Status: **{summary['status']}**",
    f"- Cases: {summary['cases']}; RTL/reference-model mismatches: {summary['rtl_reference_model_mismatches']}",
    f"- Known counterexample vector exact match: **{known_vector_exact_match}**",
    f"- Production RTL unchanged: **{RTL_HASH_AFTER == RTL_HASH_BEFORE}**",
    "",
    "## Results",
    "",
    "| Low-run delta | Low-run duration | Classification | RTL/model match | Trace rows | Event rows |",
    "|---:|---:|---|---|---:|---:|",
]
for item in all_cases:
    lines.append(f"| {item['delta_cycles']} | {item['low_run_duration_cycles']} | {item['classification']} | {item['rtl_reference_model_match']} | {item['trace_rows']} | {item['event_count']} |")
lines.extend([
    "",
    "## Boundary event excerpts",
    "",
    "| Delta | Trace index | Relative to input edge | Input | State | PC | Instruction | Sample | Shift register | Event tags |",
    "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
])
for delta in (-217, -216, -215):
    item = next(case for case in all_cases if case["delta_cycles"] == delta)
    for event in item["events"]:
        if abs(event["distance_from_input_rising_edge_cycles"]) <= 3 or "sample_instruction_state_transition" in event["event_tags"] or "sample_register_changed" in event["event_tags"] or "shift_register_changed" in event["event_tags"]:
            lines.append(f"| {delta} | {event['trace_index']} | {event['distance_from_input_rising_edge_cycles']} | {event['input_pin0']} | {event['state']} | {event['pc']} | {event['instruction_hex']} | {event['sample_reg']} | {event['shift_reg_hex']} | {', '.join(event['event_tags'])} |")
lines.extend([
    "",
    "## Interpretation",
    "",
    "The measured one-cycle transition tells us exactly where the current simulation changes classification. The cycle trace is needed to determine whether the input rising edge coincides with or passes the final data-bit sampling operation. A simultaneous edge/sample can depend on the model's cycle ordering; this experiment establishes the current simulation semantics, not physical silicon behavior.",
    "",
    f"Production RTL SHA-256: `{RTL_HASH_AFTER}`",
    f"Detailed cycle CSV: `{CSV_PATH}`",
    f"JSON report: `{json_path}`",
    f"Run directory: `{RUN_DIR}`",
    "",
])
md_path.write_text("\n".join(lines))
print("===== BOUNDARY DIAGNOSTIC SUMMARY =====")
print(json.dumps(summary, indent=2))
print("BOUNDARY CASE EVENTS (-216):")
print(json.dumps(known["events"][-24:], indent=2))
print("CYCLE CSV:", CSV_PATH)
print("JSON REPORT:", json_path)
print("MARKDOWN REPORT:", md_path)
print("RUN DIRECTORY:", RUN_DIR)
print("PRODUCTION RTL SHA256:", RTL_HASH_AFTER)
if summary["status"] != "PASS":
    raise SystemExit(1)
