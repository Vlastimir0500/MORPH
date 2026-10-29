import hashlib
import json
import os
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(os.environ["MORPH_ROOT"]).resolve()
RUN_DIR = Path(os.environ["MORPH_RUN_DIR"]).resolve()
REPORT_DIR = ROOT / "traceforge" / "reports"
RTL = ROOT / "rtl" / "morph_engine_v2.sv"
TT_RTL = ROOT / "tinytapeout-template-v2" / "src" / "morph_engine.sv"
FIRMWARE = ROOT / "protocols" / "v2_uart_rx_a6.hex"
SOURCE_TB = ROOT / "traceforge" / "rtl_run" / "morph_engine_v2_traceforge_tb.sv"
WORK = ROOT / "traceforge" / "rtl_run"
sys.path.insert(0, str(WORK))
sys.path.insert(0, str(ROOT / "sim"))
from traceforge_uart_rtl import expected_snapshot, parse_trace
from morph_isa_model_v2 import MorphISAModelV2

PHASE_SHIFT = -8
WAIT_VALUE = 211
PAYLOADS = [0x00, 0xFF, 0x55, 0x3C, 0x81, 0x7E, 0xA5, 0xA6]
PERIODS = list(range(400, 471))
NOMINAL = 436
IDLE = 10
TAIL = 240
COMMON_MIN = 412
COMMON_MAX = 459
JITTER_AMPLITUDES = [20, 40, 60, 80]
JITTER_CASES_PER_AMPLITUDE = 150
JITTER_SEED = 20261028


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reverse_byte(value):
    result = 0
    for bit in range(8):
        result = (result << 1) | ((value >> bit) & 1)
    return result


def build_uniform_frame(payload, period):
    pins = [1] * IDLE
    pins.extend([0] * period)
    for bit in range(8):
        pins.extend([((payload >> bit) & 1)] * period)
    pins.extend([1] * period)
    pins.extend([1] * TAIL)
    return pins


def build_jittered_frame(payload, durations):
    if len(durations) != 10 or min(durations) <= 0:
        raise ValueError("UART frame must have ten positive symbol durations")
    pins = [1] * IDLE
    pins.extend([0] * durations[0])
    for bit in range(8):
        pins.extend([((payload >> bit) & 1)] * durations[bit + 1])
    pins.extend([1] * durations[9])
    pins.extend([1] * TAIL)
    return pins


def build_bad_start_glitch():
    return [1] * IDLE + [0] * 12 + [1] * (NOMINAL * 10 + TAIL)


def build_bad_stop_frame(payload):
    pins = [1] * IDLE + [0] * NOMINAL
    for bit in range(8):
        pins.extend([((payload >> bit) & 1)] * NOMINAL)
    pins.extend([0] * NOMINAL)
    pins.extend([1] * TAIL)
    return pins


def compress_ranges(values):
    values = sorted(set(values))
    if not values:
        return []
    ranges = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
        else:
            ranges.append([start, previous])
            start = previous = value
    ranges.append([start, previous])
    return ranges


def main():
    global all_results, executable, program_path, vector_path, candidate_program
    originals = {
        "production_rtl_sha256": sha256(RTL),
        "tinytapeout_engine_sha256": sha256(TT_RTL),
        "production_firmware_sha256": sha256(FIRMWARE),
        "source_testbench_sha256": sha256(SOURCE_TB),
    }
    if originals["production_rtl_sha256"] != originals["tinytapeout_engine_sha256"]:
        raise SystemExit("Production RTL and TinyTapeout engine copy differ; refusing to run")

    candidate_program = [int(line.strip(), 16) for line in FIRMWARE.read_text().splitlines() if line.strip()]
    if len(candidate_program) != 18 or candidate_program[4] != 0x30D7 or candidate_program[5] != 0x30D7:
        raise SystemExit("UART firmware differs from expected baseline; refusing to patch candidate words")
    candidate_program[4] = 0x3000 | WAIT_VALUE
    candidate_program[5] = 0x3000 | WAIT_VALUE

    relative_run_dir = RUN_DIR.relative_to(ROOT).as_posix()
    tb_text = SOURCE_TB.read_text()
    for old, new in {
        "traceforge/rtl_run/morph_v2_program.hex": f"{relative_run_dir}/morph_v2_program.hex",
        "traceforge/rtl_run/morph_v2_vectors.hex": f"{relative_run_dir}/morph_v2_vectors.hex",
    }.items():
        if old not in tb_text:
            raise SystemExit(f"Expected testbench file reference not found: {old}")
        tb_text = tb_text.replace(old, new)
    tb_copy = RUN_DIR / "morph_engine_v2_candidate_robustness_tb.sv"
    tb_copy.write_text(tb_text)
    program_path = RUN_DIR / "morph_v2_program.hex"
    vector_path = RUN_DIR / "morph_v2_vectors.hex"
    build_dir = RUN_DIR / "obj_dir"
    compile_command = ["verilator", "--binary", "--timing", "-Wno-fatal", "--top-module", "morph_engine_v2_diff_tb", "--Mdir", str(build_dir), str(RTL), str(tb_copy)]
    compilation = subprocess.run(compile_command, cwd=ROOT, capture_output=True, text=True, timeout=240)
    (RUN_DIR / "verilator_build.log").write_text(compilation.stdout + "\n" + compilation.stderr)
    if compilation.returncode:
        raise RuntimeError("Verilator build failed; inspect verilator_build.log")
    executable = build_dir / "Vmorph_engine_v2_diff_tb"

    all_results = []

    def simulate_case(case, category, payload, pins, details, expected_malformed_rejection=False):
        program_path.write_text("".join(f"{word:04x}\n" for word in candidate_program + [0] * (64 - len(candidate_program))))
        vector_path.write_text("".join(f"{pin:02x}\n" for pin in pins))
        model = MorphISAModelV2()
        model.load_program(candidate_program)
        expected = [expected_snapshot(model.step(rst_n=False, pin_in=0))]
        expected.extend(expected_snapshot(model.step(pin_in=pin)) for pin in pins)
        run = subprocess.run([str(executable), f"+N={len(pins)}"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        if run.returncode:
            raise RuntimeError(f"Simulation failed for {case}:\n{run.stdout[-2000:]}\n{run.stderr[-2000:]}")
        actual = parse_trace(run.stdout)
        mismatch = None
        if len(actual) != len(expected):
            mismatch = {"kind": "trace_length", "rtl_cycles": len(actual), "model_cycles": len(expected)}
        else:
            for cycle, (got, want) in enumerate(zip(actual, expected)):
                if got != want:
                    mismatch = {"kind": "cycle_mismatch", "cycle": cycle, "rtl": list(got), "model": list(want)}
                    break
        if not actual:
            raise RuntimeError(f"No RTL trace produced for {case}")
        final = actual[-1]
        pin_out, pin_oe, observed = final[3], final[4], final[6]
        error_flag = bool((pin_out & pin_oe) & 0x80)
        core_fault = bool(final[9])
        expected_shift = reverse_byte(payload)
        if mismatch:
            classification = "rtl_model_mismatch"
        elif core_fault:
            classification = "core_fault"
        elif expected_malformed_rejection:
            classification = "malformed_rejected" if error_flag else "malformed_silent_acceptance"
        elif error_flag:
            classification = "error_flagged"
        elif observed != expected_shift:
            classification = "silent_misdecode"
        else:
            classification = "correct_decode"
        result = {
            "case": case,
            "category": category,
            "payload": f"0x{payload:02X}",
            "expected_shift_register": f"0x{expected_shift:02X}",
            "observed_shift_register": f"0x{observed:02X}",
            "error_flag_pin7": error_flag,
            "core_fault": core_fault,
            "rtl_model_match": mismatch is None,
            "first_mismatch": mismatch,
            "classification": classification,
            **details,
        }
        all_results.append(result)
        return result

    matrix_total = len(PAYLOADS) * len(PERIODS)
    jitter_total = len(JITTER_AMPLITUDES) * JITTER_CASES_PER_AMPLITUDE
    total = matrix_total + jitter_total + 2
    print("===== TRACEFORGE UART CANDIDATE ROBUSTNESS v0.1 =====", flush=True)
    print(f"Run directory: {RUN_DIR}", flush=True)
    print(f"Isolated candidate: pre-data WAIT={WAIT_VALUE}, phase shift {PHASE_SHIFT:+d} cycles", flush=True)
    print(f"Planned simulations: {total} (matrix {matrix_total}, jitter {jitter_total}, malformed 2)", flush=True)
    print("Production RTL and firmware will not be modified.", flush=True)

    completed = 0
    matrix_rows = []
    for payload in PAYLOADS:
        for period in PERIODS:
            result = simulate_case(
                f"matrix_{payload:02X}_period_{period}", "uniform_period_matrix", payload,
                build_uniform_frame(payload, period),
                {"bit_period_cycles": period, "inside_common_envelope": COMMON_MIN <= period <= COMMON_MAX},
            )
            matrix_rows.append(result)
            completed += 1
            if completed % 100 == 0:
                print(f"Progress: {completed}/{total} simulations", flush=True)

    rng = random.Random(JITTER_SEED)
    jitter_rows = []
    for amplitude in JITTER_AMPLITUDES:
        for trial in range(JITTER_CASES_PER_AMPLITUDE):
            payload = rng.choice(PAYLOADS)
            durations = [NOMINAL + rng.randint(-amplitude, amplitude) for _ in range(10)]
            result = simulate_case(
                f"jitter_amp_{amplitude}_trial_{trial:03d}", "randomized_symbol_jitter", payload,
                build_jittered_frame(payload, durations),
                {"jitter_amplitude_cycles": amplitude, "trial": trial, "random_seed": JITTER_SEED, "symbol_durations_cycles": durations},
            )
            jitter_rows.append(result)
            completed += 1
            if completed % 100 == 0:
                print(f"Progress: {completed}/{total} simulations", flush=True)

    malformed_rows = []
    malformed_rows.append(simulate_case(
        "malformed_short_start_glitch", "malformed_frame", 0x00, build_bad_start_glitch(),
        {"malformation": "12-cycle low start glitch followed by idle high", "expected_behavior": "error flag on pin 7"},
        expected_malformed_rejection=True,
    ))
    completed += 1
    malformed_rows.append(simulate_case(
        "malformed_low_stop", "malformed_frame", 0xA6, build_bad_stop_frame(0xA6),
        {"malformation": "stop symbol held low", "expected_behavior": "error flag on pin 7"},
        expected_malformed_rejection=True,
    ))
    completed += 1
    print(f"Progress: {completed}/{total} simulations", flush=True)

    matrix_counts = Counter(item["classification"] for item in matrix_rows)
    in_envelope_rows = [item for item in matrix_rows if item["inside_common_envelope"]]
    out_envelope_rows = [item for item in matrix_rows if not item["inside_common_envelope"]]
    common_envelope_all_correct = all(item["classification"] == "correct_decode" for item in in_envelope_rows)
    payload_matrix = {}
    for payload in PAYLOADS:
        selected = [item for item in matrix_rows if item["payload"] == f"0x{payload:02X}"]
        good_periods = [item["bit_period_cycles"] for item in selected if item["classification"] == "correct_decode"]
        payload_matrix[f"0x{payload:02X}"] = {
            "classification_counts": dict(sorted(Counter(item["classification"] for item in selected).items())),
            "correct_period_ranges_cycles": compress_ranges(good_periods),
            "common_envelope_all_correct": all(item["classification"] == "correct_decode" for item in selected if item["inside_common_envelope"]),
        }

    jitter_summary = {}
    for amplitude in JITTER_AMPLITUDES:
        selected = [item for item in jitter_rows if item["jitter_amplitude_cycles"] == amplitude]
        jitter_summary[str(amplitude)] = {
            "cases": len(selected),
            "classification_counts": dict(sorted(Counter(item["classification"] for item in selected).items())),
            "correct_decode_count": sum(item["classification"] == "correct_decode" for item in selected),
            "silent_misdecode_count": sum(item["classification"] == "silent_misdecode" for item in selected),
            "error_flagged_count": sum(item["classification"] == "error_flagged" for item in selected),
            "core_fault_count": sum(item["classification"] == "core_fault" for item in selected),
            "rtl_model_mismatches": sum(not item["rtl_model_match"] for item in selected),
        }

    malformed_counts = Counter(item["classification"] for item in malformed_rows)
    mismatches = [item for item in all_results if not item["rtl_model_match"]]
    after = {
        "production_rtl_sha256": sha256(RTL),
        "tinytapeout_engine_sha256": sha256(TT_RTL),
        "production_firmware_sha256": sha256(FIRMWARE),
        "source_testbench_sha256": sha256(SOURCE_TB),
    }
    sources_unchanged = after == originals
    malformed_rejection_pass = all(item["classification"] == "malformed_rejected" for item in malformed_rows)
    validation_gate_pass = not mismatches and sources_unchanged and common_envelope_all_correct and malformed_rejection_pass
    report = {
        "tool": "TRACEFORGE",
        "version": "0.1.0",
        "experiment": "Full robustness validation of isolated UART RX phase-shift candidate (-8 cycles)",
        "candidate": {"phase_shift_cycles": PHASE_SHIFT, "pre_data_wait_instruction_words": [4, 5], "wait_value_cycles_each": WAIT_VALUE, "production_firmware_modified": False},
        "parameters": {
            "payloads": [f"0x{x:02X}" for x in PAYLOADS],
            "uniform_period_range_cycles": [min(PERIODS), max(PERIODS)],
            "common_uniform_period_envelope_cycles_inclusive": [COMMON_MIN, COMMON_MAX],
            "jitter_amplitudes_cycles_each_symbol": JITTER_AMPLITUDES,
            "jitter_cases_per_amplitude": JITTER_CASES_PER_AMPLITUDE,
            "jitter_random_seed": JITTER_SEED,
            "nominal_period_cycles": NOMINAL,
        },
        "source_hashes_before": originals,
        "source_hashes_after": after,
        "summary": {
            "status": "PASS" if validation_gate_pass else "FAIL",
            "total_cases": len(all_results),
            "rtl_model_mismatches": len(mismatches),
            "production_sources_unchanged": sources_unchanged,
            "uniform_period_matrix": {
                "cases": len(matrix_rows),
                "classification_counts": dict(sorted(matrix_counts.items())),
                "common_envelope_cases": len(in_envelope_rows),
                "common_envelope_all_correct": common_envelope_all_correct,
                "outside_common_envelope_cases": len(out_envelope_rows),
                "outside_common_envelope_classification_counts": dict(sorted(Counter(item["classification"] for item in out_envelope_rows).items())),
                "per_payload": payload_matrix,
            },
            "randomized_jitter": {"cases": len(jitter_rows), "seed": JITTER_SEED, "summary_by_amplitude": jitter_summary, "classification_counts": dict(sorted(Counter(item["classification"] for item in jitter_rows).items()))},
            "malformed_frames": {"cases": len(malformed_rows), "classification_counts": dict(sorted(malformed_counts.items())), "both_rejected_as_expected": malformed_rejection_pass},
            "promotion_recommendation": "HOLD_FOR_REVIEW: this experiment is isolated candidate evidence; review timing-envelope and jitter failures, run the full release gate, and do not promote firmware automatically.",
        },
        "cases": all_results,
        "limitations": [
            "RTL simulation and independent software-model comparison only; no fabricated-silicon validation is implied.",
            "Uniform-period common envelope is the previously measured 412-459 cycle interval, tested here inclusively.",
            "Randomized jitter results depend on the declared deterministic seed and amplitude model.",
            "A PASS means cyclewise model agreement, unchanged production sources, correct decode in the measured common envelope, and malformed-frame rejection; it does not mean every period or every jittered frame decodes correctly.",
            "The candidate remains isolated and is not promoted to production firmware by this script.",
        ],
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / f"{RUN_DIR.name}.json"
    md_path = REPORT_DIR / f"{RUN_DIR.name}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    s = report["summary"]
    md = [
        "# TRACEFORGE â€” UART Candidate Robustness v0.1", "",
        f"- Validation gate: **{s['status']}**",
        f"- Total cases: {s['total_cases']}",
        f"- RTL/reference-model mismatches: {s['rtl_model_mismatches']}",
        f"- Production sources unchanged: {s['production_sources_unchanged']}",
        f"- Promotion recommendation: **HOLD FOR REVIEW**", "",
        "## Uniform-period matrix", "",
        f"- Cases: {s['uniform_period_matrix']['cases']}",
        f"- Counts: `{json.dumps(s['uniform_period_matrix']['classification_counts'], sort_keys=True)}`",
        f"- Measured common envelope: {COMMON_MIN}â€“{COMMON_MAX} cycles; {s['uniform_period_matrix']['common_envelope_cases']} cases; all correct: {s['uniform_period_matrix']['common_envelope_all_correct']}",
        f"- Outside common envelope: {s['uniform_period_matrix']['outside_common_envelope_cases']} cases; counts `{json.dumps(s['uniform_period_matrix']['outside_common_envelope_classification_counts'], sort_keys=True)}`", "",
        "| Payload | Correct period ranges (cycles) | Counts |", "|---|---|---|",
    ]
    for payload, item in payload_matrix.items():
        ranges = ", ".join(f"{start}â€“{end}" for start, end in item["correct_period_ranges_cycles"]) or "none"
        md.append(f"| {payload} | {ranges} | `{json.dumps(item['classification_counts'], sort_keys=True)}` |")
    md.extend(["", "## Randomized symbol jitter", "", f"- Cases: {len(jitter_rows)}; deterministic seed: {JITTER_SEED}", "", "| Jitter amplitude (Â± cycles per symbol) | Cases | Correct | Silent misdecode | Error flagged | Core fault | RTL/model mismatches |", "|---:|---:|---:|---:|---:|---:|---:|"])
    for amplitude in JITTER_AMPLITUDES:
        item = jitter_summary[str(amplitude)]
        md.append(f"| Â±{amplitude} | {item['cases']} | {item['correct_decode_count']} | {item['silent_misdecode_count']} | {item['error_flagged_count']} | {item['core_fault_count']} | {item['rtl_model_mismatches']} |")
    md.extend(["", "## Malformed-frame controls", "", f"- Classification counts: `{json.dumps(dict(sorted(malformed_counts.items())), sort_keys=True)}`", f"- Both rejected as expected: {malformed_rejection_pass}", "", "## Decision", "", s["promotion_recommendation"], "", f"Production RTL SHA-256: `{after['production_rtl_sha256']}`", f"Production firmware SHA-256: `{after['production_firmware_sha256']}`", ""])
    md_path.write_text("\n".join(md))

    print("===== UART CANDIDATE ROBUSTNESS SUMMARY =====", flush=True)
    print(json.dumps(s, indent=2), flush=True)
    print(f"JSON REPORT: {json_path}", flush=True)
    print(f"MARKDOWN REPORT: {md_path}", flush=True)
    print(f"RUN DIRECTORY: {RUN_DIR}", flush=True)
    print(f"PRODUCTION RTL SHA256 AFTER: {after['production_rtl_sha256']}", flush=True)
    if not validation_gate_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
