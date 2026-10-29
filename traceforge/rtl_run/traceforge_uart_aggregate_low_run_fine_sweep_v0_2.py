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

NOMINAL = int(uart.BIT_PERIOD)
IDLE = int(uart.IDLE_CYCLES)
TAIL = int(uart.TAIL_CYCLES)
PAYLOAD = 0x00
EXPECTED_SHIFT = 0x00
LOW_RUN_NOMINAL = 9 * NOMINAL
DELTA_MIN = -220
DELTA_MAX = -208
DELTA_STEP = 1
DELTAS = list(range(DELTA_MIN, DELTA_MAX + 1, DELTA_STEP))
SYMBOL_ORDER = ["start", "data0", "data1", "data2", "data3", "data4", "data5", "data6", "data7", "stop"]
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_{os.getpid()}"
RUN_DIR = WORK / f"uart_aggregate_low_run_fine_sweep_v0_2_{RUN_ID}"
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
minimized_vector_path = REPORTS / "uart_rx_minimized_counterexample_vectors.hex"
if not source_tb.is_file() or not minimized_report_path.is_file() or not minimized_vector_path.is_file():
    raise FileNotFoundError("Required UART differential bench or minimized counterexample evidence is missing")
minimized_report = json.loads(minimized_report_path.read_text())
base_offsets = list(minimized_report["minimized"]["offsets"])
if len(base_offsets) != 10:
    raise RuntimeError(f"Expected ten minimized symbol offsets, found {len(base_offsets)}")
rtl_hash_before = hashlib.sha256(rtl.read_bytes()).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_testbench_path(source: str, basename: str, target: Path):
    pattern = re.compile(r'(?P<quote>["\'])(?:[^"\']*[\\/])?' + re.escape(basename) + r'(?P=quote)')
    updated, count = pattern.subn(lambda match: match.group("quote") + str(target) + match.group("quote"), source)
    if count < 1:
        raise RuntimeError(f"Could not replace testbench filename {basename}")
    return updated, count


def make_low_run_vector(low_cycles: int) -> list[int]:
    if low_cycles <= 0:
        raise ValueError("Low-run duration must be positive")
    return [1] * IDLE + [0] * low_cycles + [1] * (NOMINAL + TAIL)


program = [int(line.strip(), 16) for line in firmware.read_text().splitlines() if line.strip()]
if len(program) != 18:
    raise RuntimeError(f"Expected 18 UART RX instructions, found {len(program)}")
source = source_tb.read_text()
source, program_replacements = replace_testbench_path(source, "morph_v2_program.hex", PROGRAM_FILE)
source, vector_replacements = replace_testbench_path(source, "morph_v2_vectors.hex", VECTOR_FILE)
ISOLATED_TB.write_text(source)

verilator = shutil.which("verilator")
if not verilator:
    raise RuntimeError("verilator not found after activating OSS CAD Suite")
compile_cmd = [verilator, "--binary", "--timing", "-Wno-fatal", "--top-module", "morph_engine_v2_diff_tb", "--Mdir", str(BUILD_DIR), str(rtl), str(ISOLATED_TB)]
compile_result = subprocess.run(compile_cmd, cwd=ROOT, capture_output=True, text=True, timeout=240)
(RUN_DIR / "verilator_build.stdout.log").write_text(compile_result.stdout)
(RUN_DIR / "verilator_build.stderr.log").write_text(compile_result.stderr)
if compile_result.returncode:
    raise RuntimeError("Isolated Verilator compilation failed; see run-directory build logs")
executable = BUILD_DIR / "Vmorph_engine_v2_diff_tb"
if not executable.is_file():
    raise RuntimeError(f"Compiled executable is missing: {executable}")

model_expected = MorphISAModelV2()
model_expected.load_program(program)
expected_shift = int(minimized_report["minimized"]["expected_shift_register"], 16)
if expected_shift != EXPECTED_SHIFT:
    raise RuntimeError(f"Payload 0x00 should expect shift register 0x00, evidence says {expected_shift:#04x}")

evaluations = 0
cases = []


def evaluate(delta: int):
    global evaluations
    evaluations += 1
    low_cycles = LOW_RUN_NOMINAL + delta
    pins = make_low_run_vector(low_cycles)
    PROGRAM_FILE.write_text("".join(f"{word:04x}\n" for word in program + [0] * (64 - len(program))))
    VECTOR_FILE.write_text("".join(f"{pin:02x}\n" for pin in pins))
    model = MorphISAModelV2()
    model.load_program(program)
    expected = [uart.expected_snapshot(model.step(rst_n=False, pin_in=0))]
    expected.extend(uart.expected_snapshot(model.step(pin_in=pin)) for pin in pins)
    run = subprocess.run([str(executable), f"+N={len(pins)}"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    if run.returncode:
        raise RuntimeError(f"UART low-run simulation failed at delta {delta}:\n{run.stdout[-2500:]}\n{run.stderr[-2500:]}")
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
        raise RuntimeError("Simulation returned an empty trace")
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
    elif observed != expected_shift:
        classification = "silent_misdecode"
    else:
        classification = "correct_decode"
    result = {
        "low_run_delta_cycles": delta,
        "low_run_duration_cycles": low_cycles,
        "nominal_low_run_duration_cycles": LOW_RUN_NOMINAL,
        "stop_high_duration_cycles": NOMINAL,
        "rtl_model_match": mismatch is None,
        "first_mismatch": mismatch,
        "expected_shift_register": f"0x{expected_shift:02X}",
        "observed_shift_register": f"0x{observed:02X}",
        "error_flag_pin7": error_flag,
        "core_fault": core_fault,
        "classification": classification,
        "input_vector_sha256": hashlib.sha256(bytes(pins)).hexdigest(),
        "cycles_compared": min(len(actual), len(expected)),
    }
    cases.append(result)
    if evaluations % 25 == 0:
        print(f"Progress: {evaluations}/{len(DELTAS)} cases; low-run delta {delta:+d} => {classification}", flush=True)
    return result


print("===== UART AGGREGATE LOW-RUN FINE SWEEP v0.2 =====")
print(f"Output directory: {RUN_DIR}")
print(f"Production RTL SHA256 before run: {rtl_hash_before}")
print(f"Nominal bit/symbol duration: {NOMINAL} cycles")
print(f"For payload 0x00, start + eight zero data bits form one continuous low interval of {LOW_RUN_NOMINAL} cycles.")
print(f"Fine boundary sweep: low-run delta {DELTA_MIN:+d}..{DELTA_MAX:+d} cycles, step {DELTA_STEP}")

baseline = evaluate(0)
known_delta = sum(base_offsets[:9])
known_case = evaluate(known_delta)
saved_vector = [int(line.strip(), 16) for line in minimized_vector_path.read_text().splitlines() if line.strip()]
known_vector = make_low_run_vector(LOW_RUN_NOMINAL + known_delta)
known_vector_matches = known_vector == saved_vector
if not known_vector_matches:
    raise RuntimeError("Aggregate low-run reconstruction did not exactly match the saved minimized counterexample vector")

for delta in DELTAS:
    if delta in (0, known_delta):
        continue
    evaluate(delta)

rtl_hash_after = sha256(rtl)
mismatches = [case for case in cases if not case["rtl_model_match"]]
counts = collections.Counter(case["classification"] for case in cases)
ordered_cases = sorted(cases, key=lambda case: case["low_run_delta_cycles"])
segments = []
for case in ordered_cases:
    classification = case["classification"]
    delta = case["low_run_delta_cycles"]
    if segments and segments[-1]["classification"] == classification and delta == segments[-1]["delta_end_cycles"] + DELTA_STEP:
        segments[-1]["delta_end_cycles"] = delta
        segments[-1]["case_count"] += 1
    else:
        segments.append({"classification": classification, "delta_start_cycles": delta, "delta_end_cycles": delta, "case_count": 1})

nominal_cases = [case for case in cases if case["low_run_delta_cycles"] == 0]
known_record = next(case for case in cases if case["low_run_delta_cycles"] == known_delta)
transition_pairs = []
for left, right in zip(ordered_cases, ordered_cases[1:]):
    if right["low_run_delta_cycles"] == left["low_run_delta_cycles"] + 1 and left["classification"] != right["classification"]:
        transition_pairs.append({
            "from_delta_cycles": left["low_run_delta_cycles"],
            "from_classification": left["classification"],
            "to_delta_cycles": right["low_run_delta_cycles"],
            "to_classification": right["classification"],
        })
report = {
    "tool": "TRACEFORGE",
    "version": "0.2.0",
    "experiment": "UART RX aggregate low-run duration sensitivity for payload 0x00",
    "status": "PASS" if not mismatches and baseline["classification"] == "correct_decode" and known_record["classification"] == "silent_misdecode" and known_vector_matches and rtl_hash_after == rtl_hash_before and bool(transition_pairs) else "FAIL",
    "scope": "Finite timing sweep using the actual V2 RTL and reference model. Simulation evidence, not proof of universal UART timing tolerance.",
    "parameters": {
        "payload": "0x00",
        "nominal_symbol_duration_cycles": NOMINAL,
        "nominal_contiguous_low_run_cycles": LOW_RUN_NOMINAL,
        "delta_min_cycles": DELTA_MIN,
        "delta_max_cycles": DELTA_MAX,
        "delta_step_cycles": DELTA_STEP,
        "tested_case_count": len(cases),
        "stop_high_duration_cycles": NOMINAL,
        "tail_cycles": TAIL,
        "minimized_counterexample_symbol_offsets_cycles": base_offsets,
        "minimized_counterexample_aggregate_low_run_delta_cycles": known_delta,
    },
    "summary": {
        "classification_counts": dict(sorted(counts.items())),
        "classification_transition_pair_count": len(transition_pairs),
        "rtl_model_mismatches": len(mismatches),
        "nominal_baseline_classification": baseline["classification"],
        "minimized_counterexample_classification": known_record["classification"],
        "saved_counterexample_vector_exact_match": known_vector_matches,
        "all_rtl_reference_model_traces_match": not mismatches,
        "production_rtl_unchanged": rtl_hash_after == rtl_hash_before,
    },
    "classification_segments_by_low_run_delta": segments,
    "classification_transition_pairs": transition_pairs,
    "known_counterexample": known_record,
    "source_hashes": {
        "production_rtl_sha256_before": rtl_hash_before,
        "production_rtl_sha256_after": rtl_hash_after,
        "uart_rx_firmware_sha256": sha256(firmware),
        "source_testbench_sha256": sha256(source_tb),
        "isolated_testbench_sha256": sha256(ISOLATED_TB),
        "minimized_counterexample_report_sha256": sha256(minimized_report_path),
        "minimized_counterexample_vector_sha256": sha256(minimized_vector_path),
    },
    "rtl_model_mismatch_samples": mismatches[:10],
    "cases": ordered_cases,
}
json_path = REPORTS / f"uart_aggregate_low_run_fine_sweep_v0_2_{RUN_ID}.json"
md_path = REPORTS / f"uart_aggregate_low_run_fine_sweep_v0_2_{RUN_ID}.md"
json_path.write_text(json.dumps(report, indent=2) + "\n")
lines = [
    "# TRACEFORGE â€” UART Aggregate Low-Run Boundary Sweep v0.2",
    "",
    f"- Status: **{report['status']}**",
    f"- Payload: `0x00`; expected shift register: `0x00`",
    f"- Nominal contiguous low-run duration: {LOW_RUN_NOMINAL} cycles",
    f"- Sweep: {DELTA_MIN:+d}â€¦{DELTA_MAX:+d} cycles, step {DELTA_STEP}; {len(cases)} cases",
    f"- Classifications: `{dict(sorted(counts.items()))}`",
    f"- Minimized counterexample aggregate delta: {known_delta} cycles; replay classification: `{known_record['classification']}`",
    f"- Saved vector exact match: **{known_vector_matches}**",
    f"- RTL/reference-model mismatches: {len(mismatches)}",
    f"- Production RTL unchanged: **{rtl_hash_after == rtl_hash_before}**",
    "",
    "## Classification intervals",
    "",
    "| Classification | Delta start (cycles) | Delta end (cycles) | Cases |",
    "|---|---:|---:|---:|",
]
for segment in segments:
    lines.append(f"| {segment['classification']} | {segment['delta_start_cycles']} | {segment['delta_end_cycles']} | {segment['case_count']} |")
lines.extend([
    "",
    "## One-cycle classification transitions",
    "",
    "| From delta | From classification | To delta | To classification |",
    "|---:|---|---:|---|",
])
for pair in transition_pairs:
    lines.append(f"| {pair['from_delta_cycles']} | {pair['from_classification']} | {pair['to_delta_cycles']} | {pair['to_classification']} |")
lines.extend([
    "",
    "## Interpretation",
    "",
    "For payload `0x00`, the start symbol and eight zero-valued data symbols create one continuous low-level interval on the input pin. This experiment therefore sweeps the observable duration of that interval rather than treating visually identical adjacent low symbols as independently observable edges.",
    "",
    "The known minimized waveform is reconstructed from the sum of its first nine symbol offsets and must match the saved pin vector byte-for-byte. This fine sweep uses 1-cycle increments around the transition seen in v0.1; measured boundaries apply only to this firmware and timing model.",
    "",
    f"Production RTL SHA-256: `{rtl_hash_after}`",
    f"JSON report: `{json_path}`",
    f"Run directory: `{RUN_DIR}`",
    "",
])
md_path.write_text("\n".join(lines))
print("===== UART AGGREGATE LOW-RUN SWEEP SUMMARY =====")
print(json.dumps(report["summary"], indent=2))
print("CLASSIFICATION SEGMENTS:")
print(json.dumps(segments, indent=2))
print("ONE-CYCLE TRANSITIONS:")
print(json.dumps(transition_pairs, indent=2))
print("STATUS:", report["status"])
print("JSON REPORT:", json_path)
print("MARKDOWN REPORT:", md_path)
print("RUN DIRECTORY:", RUN_DIR)
print("PRODUCTION RTL SHA256:", rtl_hash_after)
if report["status"] != "PASS":
    raise SystemExit(1)
