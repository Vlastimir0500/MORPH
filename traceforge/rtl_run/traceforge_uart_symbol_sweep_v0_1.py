from __future__ import annotations
import collections
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"Required evidence file is missing: {path}")
    return json.loads(path.read_text())


def reverse_byte(value: int) -> int:
    return int(f"{value:08b}"[::-1], 2)


def build_frame(payload: int, offsets: list[int]):
    if len(offsets) != 10:
        raise ValueError("UART frame must have ten symbols: start, 8 data, stop")
    durations = [NOMINAL + offset for offset in offsets]
    if min(durations) <= 0:
        raise ValueError("Every symbol duration must be positive")
    pins = [1] * IDLE
    pins.extend([0] * durations[0])
    for bit in range(8):
        pins.extend([((payload >> bit) & 1)] * durations[bit + 1])
    pins.extend([1] * durations[9])
    pins.extend([1] * TAIL)
    return pins, durations


def replace_testbench_path(source: str, basename: str, target: Path):
    pattern = re.compile(r'(?P<quote>["\'])(?:[^"\']*[\\/])?' + re.escape(basename) + r'(?P=quote)')
    replacement = lambda match: match.group("quote") + str(target) + match.group("quote")
    updated, count = pattern.subn(replacement, source)
    if count < 1:
        raise RuntimeError(f"Could not isolate testbench path for {basename}; no matching quoted filename found")
    return updated, count


NOMINAL = int(uart.BIT_PERIOD)
IDLE = int(uart.IDLE_CYCLES)
TAIL = int(uart.TAIL_CYCLES)
PAYLOAD = 0x00
GRID = list(range(-80, 81, 8))
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_{os.getpid()}"
RUN_DIR = WORK / f"uart_symbol_sweep_v0_1_{RUN_ID}"
RUN_DIR.mkdir(parents=True, exist_ok=False)
BUILD_DIR = RUN_DIR / "obj_dir"
BUILD_DIR.mkdir()
PROGRAM_FILE = RUN_DIR / "morph_v2_program.hex"
VECTOR_FILE = RUN_DIR / "morph_v2_vectors.hex"
ISOLATED_TB = RUN_DIR / "morph_engine_v2_traceforge_tb.sv"

rtl = ROOT / "rtl" / "morph_engine_v2.sv"
source_tb = WORK / "morph_engine_v2_traceforge_tb.sv"
firmware = ROOT / "protocols" / "v2_uart_rx_a6.hex"
minimized_report_path = REPORTS / "uart_rx_minimized_counterexample.json"
minimized_report = read_json(minimized_report_path)
rtl_hash_before = sha256(rtl)
base_offsets = list(minimized_report["minimized"]["offsets"])
if len(base_offsets) != 10:
    raise RuntimeError(f"Expected ten offsets in minimized counterexample, found {len(base_offsets)}")
expected_shift = int(minimized_report["minimized"]["expected_shift_register"], 16)

program = [int(line.strip(), 16) for line in firmware.read_text().splitlines() if line.strip()]
if len(program) != 18:
    raise RuntimeError(f"Expected 18 UART RX instructions, found {len(program)}")

text = source_tb.read_text()
text, program_replacements = replace_testbench_path(text, "morph_v2_program.hex", PROGRAM_FILE)
text, vector_replacements = replace_testbench_path(text, "morph_v2_vectors.hex", VECTOR_FILE)
ISOLATED_TB.write_text(text)

verilator = shutil.which("verilator")
if not verilator:
    raise RuntimeError("verilator unavailable; activate OSS CAD Suite before running")
compile_cmd = [
    verilator, "--binary", "--timing", "-Wno-fatal",
    "--top-module", "morph_engine_v2_diff_tb",
    "--Mdir", str(BUILD_DIR), str(rtl), str(ISOLATED_TB)
]
compile_result = subprocess.run(compile_cmd, cwd=ROOT, capture_output=True, text=True, timeout=240)
(RUN_DIR / "verilator_build.stdout.log").write_text(compile_result.stdout)
(RUN_DIR / "verilator_build.stderr.log").write_text(compile_result.stderr)
if compile_result.returncode:
    raise RuntimeError("Isolated Verilator compile failed; see " + str(RUN_DIR / "verilator_build.stderr.log"))
executable = BUILD_DIR / "Vmorph_engine_v2_diff_tb"
if not executable.is_file():
    raise RuntimeError(f"Verilator executable not found: {executable}")

expected_nominal = reverse_byte(PAYLOAD)
if expected_shift != expected_nominal:
    raise RuntimeError(f"Saved counterexample expected shift {expected_shift:#04x} does not match payload-derived value {expected_nominal:#04x}")
evaluations = 0
cases = []


def evaluate(context: str, symbol_index: int | None, varied_offset: int | None, offsets: list[int]):
    global evaluations
    evaluations += 1
    pins, durations = build_frame(PAYLOAD, offsets)
    PROGRAM_FILE.write_text("".join(f"{word:04x}\n" for word in program + [0] * (64 - len(program))))
    VECTOR_FILE.write_text("".join(f"{pin:02x}\n" for pin in pins))

    model = MorphISAModelV2()
    model.load_program(program)
    expected = [uart.expected_snapshot(model.step(rst_n=False, pin_in=0))]
    expected.extend(uart.expected_snapshot(model.step(pin_in=pin)) for pin in pins)
    run = subprocess.run([str(executable), f"+N={len(pins)}"], cwd=ROOT,
                         capture_output=True, text=True, timeout=120)
    if run.returncode:
        raise RuntimeError(f"UART sweep simulation failed ({context}, symbol={symbol_index}, offset={varied_offset}):\n{run.stdout[-2000:]}\n{run.stderr[-2000:]}")
    actual = uart.parse_trace(run.stdout)
    mismatch = None
    if len(actual) != len(expected):
        mismatch = {"kind": "trace_length", "rtl_cycles": len(actual), "model_cycles": len(expected)}
    else:
        for index, (got, want) in enumerate(zip(actual, expected)):
            if got != want:
                mismatch = {"kind": "cycle_mismatch", "trace_index": index, "rtl": list(got), "model": list(want)}
                break
    if not actual:
        raise RuntimeError("Isolated UART sweep simulator returned an empty trace")

    final = actual[-1]
    pin_out, pin_oe = final[3], final[4]
    observed = final[6]
    error_flag = bool((pin_out & pin_oe) & 0x80)
    core_fault = bool(final[9])
    if mismatch:
        classification = "rtl_model_mismatch"
    elif error_flag:
        classification = "error_flagged"
    elif core_fault:
        classification = "core_fault"
    elif observed != expected_nominal:
        classification = "silent_misdecode"
    else:
        classification = "correct_decode"
    record = {
        "context": context,
        "symbol_index": symbol_index,
        "symbol_name": ["start", "data0", "data1", "data2", "data3", "data4", "data5", "data6", "data7", "stop"][symbol_index] if symbol_index is not None else "baseline",
        "varied_offset_cycles": varied_offset,
        "offsets_cycles": offsets,
        "durations_cycles": durations,
        "rtl_model_match": mismatch is None,
        "first_mismatch": mismatch,
        "expected_shift_register": f"0x{expected_nominal:02X}",
        "observed_shift_register": f"0x{observed:02X}",
        "error_flag_pin7": error_flag,
        "core_fault": core_fault,
        "classification": classification,
        "cycles_compared": min(len(actual), len(expected)),
    }
    cases.append(record)
    if evaluations % 50 == 0:
        print(f"Progress: {evaluations} simulations; latest {context} symbol={symbol_index} offset={varied_offset} => {classification}", flush=True)
    return record


print("===== UART SYMBOL-BY-SYMBOL TIMING SWEEP v0.1 =====")
print(f"Output directory: {RUN_DIR}")
print(f"Production RTL SHA256 before run: {sha256(rtl)}")
print(f"Nominal bit/symbol duration: {NOMINAL} cycles")
print(f"Coarse offset grid: {GRID[0]}..{GRID[-1]} cycles, step 8")
print("Sweeps: each symbol independently varied over a nominal clean frame, then over the minimized failing frame.")

minimized_baseline = evaluate("minimized_baseline", None, None, base_offsets)
if minimized_baseline["classification"] != "silent_misdecode" or not minimized_baseline["rtl_model_match"]:
    raise RuntimeError("Saved minimized UART counterexample did not reproduce as a cycle-matching silent misdecode")

for symbol in range(10):
    for offset in GRID:
        offsets = [0] * 10
        offsets[symbol] = offset
        evaluate("nominal_context", symbol, offset, offsets)

for symbol in range(10):
    offsets_to_try = sorted(set(GRID + [base_offsets[symbol]]))
    for offset in offsets_to_try:
        offsets = list(base_offsets)
        offsets[symbol] = offset
        evaluate("minimized_context", symbol, offset, offsets)

# Invariant: the only accepted RTL/model relation in this run is cycle-by-cycle equality.
mismatches = [case for case in cases if not case["rtl_model_match"]]
nominal_cases = [case for case in cases if case["context"] == "nominal_context"]
minimized_cases = [case for case in cases if case["context"] == "minimized_context"]
nominal_single_symbol_silent = [case for case in nominal_cases if case["classification"] == "silent_misdecode"]
nominal_classification_counts = collections.Counter(case["classification"] for case in nominal_cases)


def compress_offsets(values: list[int], step: int = 8):
    values = sorted(set(values))
    if not values:
        return []
    ranges = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + step:
            previous = value
        else:
            ranges.append([start, previous] if start != previous else [start])
            start = previous = value
    ranges.append([start, previous] if start != previous else [start])
    return ranges

per_symbol = []
for symbol in range(10):
    nc = [case for case in nominal_cases if case["symbol_index"] == symbol]
    mc = [case for case in minimized_cases if case["symbol_index"] == symbol]
    nominal_counts = collections.Counter(case["classification"] for case in nc)
    minimized_counts = collections.Counter(case["classification"] for case in mc)
    silent_offsets = [case["varied_offset_cycles"] for case in mc if case["classification"] == "silent_misdecode"]
    recovery_offsets = [case["varied_offset_cycles"] for case in mc if case["classification"] == "correct_decode"]
    error_offsets = [case["varied_offset_cycles"] for case in mc if case["classification"] == "error_flagged"]
    per_symbol.append({
        "symbol_index": symbol,
        "symbol_name": nc[0]["symbol_name"] if nc else mc[0]["symbol_name"],
        "nominal_context": {
            "tested_offsets_cycles": [case["varied_offset_cycles"] for case in nc],
            "classification_counts": dict(sorted(nominal_counts.items())),
            "silent_misdecode_offsets_cycles": [case["varied_offset_cycles"] for case in nc if case["classification"] == "silent_misdecode"],
            "rtl_model_mismatches": sum(not case["rtl_model_match"] for case in nc),
        },
        "minimized_context": {
            "fixed_other_symbol_offsets_cycles": [value for index, value in enumerate(base_offsets) if index != symbol],
            "tested_offsets_cycles": [case["varied_offset_cycles"] for case in mc],
            "classification_counts": dict(sorted(minimized_counts.items())),
            "silent_misdecode_offset_ranges_step8": compress_offsets(silent_offsets),
            "single_coordinate_recovery_offsets_cycles": recovery_offsets,
            "error_flagged_offsets_cycles": error_offsets,
            "rtl_model_mismatches": sum(not case["rtl_model_match"] for case in mc),
        },
    })

rtl_hash_after = sha256(rtl)
source_hashes = {
    "production_rtl_sha256_before": rtl_hash_before,
    "production_rtl_sha256_after": rtl_hash_after,
    "uart_rx_firmware_sha256": sha256(firmware),
    "source_testbench_sha256": sha256(source_tb),
    "isolated_testbench_sha256": sha256(ISOLATED_TB),
    "minimized_counterexample_report_sha256": sha256(minimized_report_path),
}
report = {
    "tool": "TRACEFORGE",
    "version": "0.1.0",
    "experiment": "UART one-symbol-at-a-time timing sensitivity around nominal and minimized failing frames",
    "status": "PASS" if not mismatches and minimized_baseline["classification"] == "silent_misdecode" and rtl_hash_after == rtl_hash_before else "FAIL",
    "scope": "Finite coarse grid; simulation evidence, not exhaustive proof or a universal UART specification.",
    "parameters": {
        "payload": "0x00",
        "nominal_symbol_duration_cycles": NOMINAL,
        "idle_cycles": IDLE,
        "tail_cycles": TAIL,
        "coarse_offset_grid_cycles": GRID,
        "step_cycles": 8,
        "symbol_order": ["start", "data0", "data1", "data2", "data3", "data4", "data5", "data6", "data7", "stop"],
        "minimized_counterexample_offsets_cycles": base_offsets,
        "expected_shift_register": f"0x{expected_nominal:02X}",
    },
    "summary": {
        "rtl_model_mismatches": len(mismatches),
        "nominal_context_cases": len(nominal_cases),
        "nominal_context_classification_counts": dict(sorted(nominal_classification_counts.items())),
        "single_symbol_deviation_alone_caused_silent_misdecode": bool(nominal_single_symbol_silent),
        "minimized_context_cases": len(minimized_cases),
        "minimized_context_silent_misdecode_cases": sum(case["classification"] == "silent_misdecode" for case in minimized_cases),
        "minimized_context_correct_decode_cases": sum(case["classification"] == "correct_decode" for case in minimized_cases),
        "minimized_context_error_flagged_cases": sum(case["classification"] == "error_flagged" for case in minimized_cases),
        "total_simulation_evaluations_including_baseline": evaluations,
        "minimized_baseline_reproduced": minimized_baseline["classification"] == "silent_misdecode",
        "all_rtl_reference_model_traces_match": not mismatches,
        "production_rtl_unchanged": rtl_hash_after == rtl_hash_before,
    },
    "per_symbol_summary": per_symbol,
    "source_hashes": source_hashes,
    "rtl_model_mismatch_samples": mismatches[:10],
    "cases": cases,
}

report_json = REPORTS / f"uart_symbol_sweep_v0_1_{RUN_ID}.json"
report_md = REPORTS / f"uart_symbol_sweep_v0_1_{RUN_ID}.md"
report_json.write_text(json.dumps(report, indent=2) + "\n")
lines = [
    "# TRACEFORGE â€” UART Symbol Timing Sensitivity v0.1",
    "",
    f"- Status: **{report['status']}**",
    f"- Payload: `0x{PAYLOAD:02X}`; expected shift register: `{expected_nominal:#04x}`",
    f"- Nominal duration: {NOMINAL} cycles; coarse sweep step: 8 cycles",
    f"- Simulation evaluations: {evaluations}",
    f"- Nominal-context cases: {len(nominal_cases)}; classifications: `{dict(sorted(nominal_classification_counts.items()))}`",
    f"- Did a single symbol offset alone produce a silent misdecode on a nominal frame? **{bool(nominal_single_symbol_silent)}**",
    f"- Minimized-context cases: {len(minimized_cases)}",
    f"- Minimized-context silent-misdecode cases: {sum(case['classification'] == 'silent_misdecode' for case in minimized_cases)}",
    f"- RTL/reference-model mismatches: {len(mismatches)}",
    f"- Production RTL unchanged: **{rtl_hash_after == rtl_hash_before}**",
    "",
    "## Per-symbol results",
    "",
    "| Symbol | Nominal context: classifications | Minimized context: classifications | Minimized offsets that recover correct decode |",
    "|---|---|---|---|",
]
for item in per_symbol:
    nominal_summary = item["nominal_context"]["classification_counts"]
    minimized_summary = item["minimized_context"]["classification_counts"]
    recoveries = item["minimized_context"]["single_coordinate_recovery_offsets_cycles"]
    lines.append(f"| {item['symbol_name']} | `{nominal_summary}` | `{minimized_summary}` | `{recoveries}` |")
lines.extend([
    "",
    "## Interpretation",
    "",
    "Nominal-context sweeps vary one symbol while all other symbols remain nominal. Minimized-context sweeps vary one symbol while holding the other nine at the saved minimized counterexample values.",
    "",
    "The offset grid is coarse (8 cycles) and bounded to âˆ’80â€¦+80 cycles. It characterizes sensitivity on that grid only; it does not prove behavior between grid points or establish a universal UART tolerance.",
    "",
    f"Production RTL SHA-256: `{rtl_hash_after}`",
    f"JSON report: `{report_json}`",
    f"Run directory: `{RUN_DIR}`",
    "",
])
report_md.write_text("\n".join(lines))

print("===== UART SYMBOL SWEEP SUMMARY =====")
print(json.dumps(report["summary"], indent=2))
print("STATUS:", report["status"])
print("JSON REPORT:", report_json)
print("MARKDOWN REPORT:", report_md)
print("RUN DIRECTORY:", RUN_DIR)
print("PRODUCTION RTL SHA256:", rtl_hash_after)
if report["status"] != "PASS":
    raise SystemExit(1)
