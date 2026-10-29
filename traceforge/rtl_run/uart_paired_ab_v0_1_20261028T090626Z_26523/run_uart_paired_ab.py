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
BOUNDARY_DELTAS = list(range(-220, -207))
MINIMIZED_DURATIONS = [427, 436, 421, 379, 436, 400, 396, 377, 436, 436]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reverse_byte(value):
    result = 0
    for bit in range(8):
        result = (result << 1) | ((value >> bit) & 1)
    return result


def build_uniform_frame(payload, period):
    pins = [1] * IDLE + [0] * period
    for bit in range(8):
        pins.extend([((payload >> bit) & 1)] * period)
    pins.extend([1] * period)
    pins.extend([1] * TAIL)
    return pins


def build_jittered_frame(payload, durations):
    if len(durations) != 10 or min(durations) <= 0:
        raise ValueError("UART frame must have ten positive symbol durations")
    pins = [1] * IDLE + [0] * durations[0]
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


def build_aggregate_low_run(delta):
    low_cycles = 9 * NOMINAL + delta
    return [1] * IDLE + [0] * low_cycles + [1] * NOMINAL + [1] * TAIL


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


def count_class(rows, classification):
    return sum(row["classification"] == classification for row in rows)


def main():
    originals = {
        "production_rtl_sha256": sha256(RTL),
        "tinytapeout_engine_sha256": sha256(TT_RTL),
        "production_firmware_sha256": sha256(FIRMWARE),
        "source_testbench_sha256": sha256(SOURCE_TB),
    }
    if originals["production_rtl_sha256"] != originals["tinytapeout_engine_sha256"]:
        raise SystemExit("Production RTL and TinyTapeout engine copy differ; refusing to run")

    baseline_program = [int(line.strip(), 16) for line in FIRMWARE.read_text().splitlines() if line.strip()]
    if len(baseline_program) != 18 or baseline_program[4] != 0x30D7 or baseline_program[5] != 0x30D7:
        raise SystemExit("UART firmware differs from expected baseline; refusing to run paired experiment")
    candidate_program = baseline_program.copy()
    candidate_program[4] = 0x30D3
    candidate_program[5] = 0x30D3
    programs = {"baseline": baseline_program, "candidate_minus8": candidate_program}

    relative_run_dir = RUN_DIR.relative_to(ROOT).as_posix()
    tb_text = SOURCE_TB.read_text()
    for old, new in {
        "traceforge/rtl_run/morph_v2_program.hex": f"{relative_run_dir}/morph_v2_program.hex",
        "traceforge/rtl_run/morph_v2_vectors.hex": f"{relative_run_dir}/morph_v2_vectors.hex",
    }.items():
        if old not in tb_text:
            raise SystemExit(f"Expected testbench file reference not found: {old}")
        tb_text = tb_text.replace(old, new)
    tb_copy = RUN_DIR / "morph_engine_v2_paired_ab_tb.sv"
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

    def simulate(program_name, program, case, category, payload, pins, details, expected_malformed=False):
        program_path.write_text("".join(f"{word:04x}\n" for word in program + [0] * (64 - len(program))))
        vector_path.write_text("".join(f"{pin:02x}\n" for pin in pins))
        model = MorphISAModelV2()
        model.load_program(program)
        expected = [expected_snapshot(model.step(rst_n=False, pin_in=0))]
        expected.extend(expected_snapshot(model.step(pin_in=pin)) for pin in pins)
        run = subprocess.run([str(executable), f"+N={len(pins)}"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        if run.returncode:
            raise RuntimeError(f"Simulation failed for {program_name}/{case}:\n{run.stdout[-2000:]}\n{run.stderr[-2000:]}")
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
            raise RuntimeError(f"No RTL trace produced for {program_name}/{case}")
        final = actual[-1]
        pin_out, pin_oe, observed = final[3], final[4], final[6]
        error_flag = bool((pin_out & pin_oe) & 0x80)
        core_fault = bool(final[9])
        expected_shift = reverse_byte(payload)
        if mismatch:
            classification = "rtl_model_mismatch"
        elif core_fault:
            classification = "core_fault"
        elif expected_malformed:
            classification = "malformed_rejected" if error_flag else "malformed_silent_acceptance"
        elif error_flag:
            classification = "error_flagged"
        elif observed != expected_shift:
            classification = "silent_misdecode"
        else:
            classification = "correct_decode"
        return {
            "program": program_name,
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

    specs = []
    for payload in PAYLOADS:
        for period in PERIODS:
            specs.append((f"matrix_{payload:02X}_period_{period}", "uniform_period_matrix", payload, build_uniform_frame(payload, period), {"bit_period_cycles": period, "inside_common_envelope": COMMON_MIN <= period <= COMMON_MAX}, False))

    rng = random.Random(JITTER_SEED)
    for amplitude in JITTER_AMPLITUDES:
        for trial in range(JITTER_CASES_PER_AMPLITUDE):
            payload = rng.choice(PAYLOADS)
            durations = [NOMINAL + rng.randint(-amplitude, amplitude) for _ in range(10)]
            specs.append((f"jitter_amp_{amplitude}_trial_{trial:03d}", "randomized_symbol_jitter", payload, build_jittered_frame(payload, durations), {"jitter_amplitude_cycles": amplitude, "trial": trial, "random_seed": JITTER_SEED, "symbol_durations_cycles": durations}, False))

    specs.append(("malformed_short_start_glitch", "malformed_frame", 0x00, build_bad_start_glitch(), {"malformation": "12-cycle low start glitch followed by idle high", "expected_behavior": "error flag on pin 7"}, True))
    specs.append(("malformed_low_stop", "malformed_frame", 0xA6, build_bad_stop_frame(0xA6), {"malformation": "stop symbol held low", "expected_behavior": "error flag on pin 7"}, True))
    specs.append(("minimized_counterexample_payload00", "minimized_counterexample", 0x00, build_jittered_frame(0x00, MINIMIZED_DURATIONS), {"symbol_durations_cycles": MINIMIZED_DURATIONS, "minimizer_seed": 26261051}, False))
    for delta in BOUNDARY_DELTAS:
        specs.append((f"aggregate_low_run_delta_{delta:+d}", "aggregate_low_run_boundary", 0x00, build_aggregate_low_run(delta), {"aggregate_low_run_delta_cycles": delta, "aggregate_low_run_cycles": 9 * NOMINAL + delta}, False))

    if len(specs) != 1184:
        raise SystemExit(f"Unexpected test vector count: {len(specs)}; expected 1184")
    paired = []
    print("===== TRACEFORGE UART PAIRED A/B v0.1 =====", flush=True)
    print(f"Run directory: {RUN_DIR}", flush=True)
    print("A: production baseline WAIT=215; B: isolated candidate WAIT=211 (-8 cycles)", flush=True)
    print(f"Identical stimulus cases per variant: {len(specs)}; total simulations: {len(specs) * 2}", flush=True)
    print("Production RTL and firmware are read-only for this run.", flush=True)

    for index, spec in enumerate(specs, start=1):
        case, category, payload, pins, details, malformed = spec
        base = simulate("baseline", baseline_program, case, category, payload, pins, details, malformed)
        cand = simulate("candidate_minus8", candidate_program, case, category, payload, pins, details, malformed)
        paired.append({"case": case, "category": category, "baseline": base, "candidate_minus8": cand, "same_stimulus": True})
        if index % 50 == 0 or index == len(specs):
            print(f"Progress: {index}/{len(specs)} paired cases ({index*2}/{len(specs)*2} simulations)", flush=True)

    by_program = {name: [pair[name] for pair in paired] for name in programs}
    summaries = {}
    for name, rows in by_program.items():
        matrix = [row for row in rows if row["category"] == "uniform_period_matrix"]
        jitter = [row for row in rows if row["category"] == "randomized_symbol_jitter"]
        malformed = [row for row in rows if row["category"] == "malformed_frame"]
        minimized = [row for row in rows if row["category"] == "minimized_counterexample"]
        boundary = [row for row in rows if row["category"] == "aggregate_low_run_boundary"]
        common = [row for row in matrix if row["inside_common_envelope"]]
        payload_summary = {}
        for payload in PAYLOADS:
            selected = [row for row in matrix if row["payload"] == f"0x{payload:02X}"]
            correct_periods = [row["bit_period_cycles"] for row in selected if row["classification"] == "correct_decode"]
            payload_summary[f"0x{payload:02X}"] = {
                "classification_counts": dict(sorted(Counter(row["classification"] for row in selected).items())),
                "correct_period_ranges_cycles": compress_ranges(correct_periods),
            }
        jitter_by_amp = {}
        for amp in JITTER_AMPLITUDES:
            selected = [row for row in jitter if row["jitter_amplitude_cycles"] == amp]
            jitter_by_amp[str(amp)] = {
                "cases": len(selected),
                "classification_counts": dict(sorted(Counter(row["classification"] for row in selected).items())),
                "correct": count_class(selected, "correct_decode"),
                "silent_misdecode": count_class(selected, "silent_misdecode"),
                "error_flagged": count_class(selected, "error_flagged"),
            }
        summaries[name] = {
            "cases": len(rows),
            "classification_counts_all_cases": dict(sorted(Counter(row["classification"] for row in rows).items())),
            "rtl_model_mismatches": sum(not row["rtl_model_match"] for row in rows),
            "uniform_period_matrix": {
                "cases": len(matrix),
                "classification_counts": dict(sorted(Counter(row["classification"] for row in matrix).items())),
                "common_envelope_cases": len(common),
                "common_envelope_all_correct": all(row["classification"] == "correct_decode" for row in common),
                "outside_common_envelope_counts": dict(sorted(Counter(row["classification"] for row in matrix if not row["inside_common_envelope"]).items())),
                "per_payload": payload_summary,
            },
            "randomized_jitter": {
                "cases": len(jitter),
                "seed": JITTER_SEED,
                "classification_counts": dict(sorted(Counter(row["classification"] for row in jitter).items())),
                "by_amplitude": jitter_by_amp,
            },
            "malformed_frames": {
                "cases": len(malformed),
                "classification_counts": dict(sorted(Counter(row["classification"] for row in malformed).items())),
                "both_rejected_as_expected": all(row["classification"] == "malformed_rejected" for row in malformed),
            },
            "minimized_counterexample": [{"case": row["case"], "classification": row["classification"], "observed": row["observed_shift_register"], "error_flagged": row["error_flag_pin7"]} for row in minimized],
            "aggregate_low_run_boundary": [{"delta_cycles": row["aggregate_low_run_delta_cycles"], "classification": row["classification"], "observed": row["observed_shift_register"], "error_flagged": row["error_flag_pin7"]} for row in boundary],
        }

    transitions = Counter((pair["baseline"]["classification"], pair["candidate_minus8"]["classification"]) for pair in paired)
    baseline_correct = count_class(by_program["baseline"], "correct_decode")
    candidate_correct = count_class(by_program["candidate_minus8"], "correct_decode")
    baseline_silent = count_class(by_program["baseline"], "silent_misdecode")
    candidate_silent = count_class(by_program["candidate_minus8"], "silent_misdecode")
    baseline_flagged = count_class(by_program["baseline"], "error_flagged")
    candidate_flagged = count_class(by_program["candidate_minus8"], "error_flagged")
    improved = [p for p in paired if p["baseline"]["classification"] != "correct_decode" and p["candidate_minus8"]["classification"] == "correct_decode"]
    regressed = [p for p in paired if p["baseline"]["classification"] == "correct_decode" and p["candidate_minus8"]["classification"] != "correct_decode"]
    improved_safety = [p for p in paired if p["baseline"]["classification"] == "silent_misdecode" and p["candidate_minus8"]["classification"] == "error_flagged"]
    degraded_safety = [p for p in paired if p["baseline"]["classification"] == "error_flagged" and p["candidate_minus8"]["classification"] == "silent_misdecode"]

    after = {
        "production_rtl_sha256": sha256(RTL),
        "tinytapeout_engine_sha256": sha256(TT_RTL),
        "production_firmware_sha256": sha256(FIRMWARE),
        "source_testbench_sha256": sha256(SOURCE_TB),
    }
    sources_unchanged = after == originals
    all_model_matches = all(row["rtl_model_match"] for rows in by_program.values() for row in rows)
    gate_pass = sources_unchanged and all_model_matches and all(summaries[name]["uniform_period_matrix"]["common_envelope_all_correct"] for name in programs) and all(summaries[name]["malformed_frames"]["both_rejected_as_expected"] for name in programs)
    report = {
        "tool": "TRACEFORGE",
        "version": "0.1.0",
        "experiment": "Paired UART RX baseline versus isolated -8-cycle phase candidate using identical deterministic stimuli",
        "candidate": {"baseline_wait_words_4_5": 215, "candidate_wait_words_4_5": 211, "phase_shift_cycles": -8, "production_firmware_modified": False},
        "parameters": {
            "payloads": [f"0x{x:02X}" for x in PAYLOADS],
            "uniform_period_range_cycles": [min(PERIODS), max(PERIODS)],
            "common_uniform_period_envelope_cycles_inclusive": [COMMON_MIN, COMMON_MAX],
            "jitter_amplitudes_cycles_each_symbol": JITTER_AMPLITUDES,
            "jitter_cases_per_amplitude": JITTER_CASES_PER_AMPLITUDE,
            "jitter_seed": JITTER_SEED,
            "minimized_counterexample_durations_cycles": MINIMIZED_DURATIONS,
            "aggregate_low_run_deltas_cycles": BOUNDARY_DELTAS,
        },
        "source_hashes_before": originals,
        "source_hashes_after": after,
        "summary": {
            "status": "PASS" if gate_pass else "FAIL",
            "paired_stimulus_cases": len(paired),
            "total_simulations": len(paired) * 2,
            "rtl_model_mismatches": sum(1 for rows in by_program.values() for row in rows if not row["rtl_model_match"]),
            "production_sources_unchanged": sources_unchanged,
            "baseline": summaries["baseline"],
            "candidate_minus8": summaries["candidate_minus8"],
            "paired_delta_candidate_minus_baseline": {
                "correct_decode_delta": candidate_correct - baseline_correct,
                "silent_misdecode_delta": candidate_silent - baseline_silent,
                "error_flagged_delta": candidate_flagged - baseline_flagged,
                "baseline_not_correct_but_candidate_correct_cases": len(improved),
                "baseline_correct_but_candidate_not_correct_cases": len(regressed),
                "silent_misdecode_to_error_flagged_cases": len(improved_safety),
                "error_flagged_to_silent_misdecode_cases": len(degraded_safety),
                "classification_transition_counts": [{"baseline": a, "candidate_minus8": b, "count": n} for (a, b), n in sorted(transitions.items())],
                "counterexample_baseline": summaries["baseline"]["minimized_counterexample"],
                "counterexample_candidate": summaries["candidate_minus8"]["minimized_counterexample"],
            },
            "promotion_recommendation": "HOLD_FOR_REVIEW: use paired outcome deltas and the stated UART requirements to decide whether the firmware phase shift is acceptable; do not promote automatically.",
        },
        "paired_cases": paired,
        "limitations": [
            "RTL simulation and software reference-model comparison only; no fabricated-silicon validation is implied.",
            "The measured common envelope is tested inclusively at 412-459 cycles; this is a previously measured test envelope, not a claim of standards certification.",
            "Jitter scenarios are deterministic and bounded by the specified per-symbol amplitude; they do not cover every possible input waveform.",
            "An experiment PASS only means both configurations match the reference model, production sources remain unchanged, both pass the specified common-envelope controls, and both reject the two malformed controls.",
            "The candidate is isolated and is not promoted to production firmware by this script.",
        ],
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / f"{RUN_DIR.name}.json"
    md_path = REPORT_DIR / f"{RUN_DIR.name}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    s = report["summary"]
    md = [
        "# TRACEFORGE â€” UART Paired A/B v0.1", "",
        f"- Experiment gate: **{s['status']}**",
        f"- Paired cases: {len(paired)}; total RTL simulations: {len(paired)*2}",
        f"- RTL/reference-model mismatches: {s['rtl_model_mismatches']}",
        f"- Production sources unchanged: {sources_unchanged}", "",
        "## Top-line comparison", "",
        "| Metric | Baseline WAIT=215 | Candidate WAIT=211 | Delta (candidate âˆ’ baseline) |",
        "|---|---:|---:|---:|",
        f"| Correct decodes | {baseline_correct} | {candidate_correct} | {candidate_correct-baseline_correct:+d} |",
        f"| Silent misdecodes | {baseline_silent} | {candidate_silent} | {candidate_silent-baseline_silent:+d} |",
        f"| Error flagged | {baseline_flagged} | {candidate_flagged} | {candidate_flagged-baseline_flagged:+d} |",
        f"| Candidate resolves baseline non-correct case | â€” | â€” | {len(improved)} cases |",
        f"| Candidate regresses baseline correct case | â€” | â€” | {len(regressed)} cases |",
        f"| Silent misdecode â†’ error flagged | â€” | â€” | {len(improved_safety)} cases |",
        f"| Error flagged â†’ silent misdecode | â€” | â€” | {len(degraded_safety)} cases |", "",
        "## Uniform-period matrix", "",
        f"- Baseline counts: `{json.dumps(summaries['baseline']['uniform_period_matrix']['classification_counts'], sort_keys=True)}`",
        f"- Candidate counts: `{json.dumps(summaries['candidate_minus8']['uniform_period_matrix']['classification_counts'], sort_keys=True)}`",
        f"- Both common-envelope controls pass: {summaries['baseline']['uniform_period_matrix']['common_envelope_all_correct']} / {summaries['candidate_minus8']['uniform_period_matrix']['common_envelope_all_correct']}", "",
        "## Jitter and malformed-frame controls", "",
        f"- Baseline jitter: `{json.dumps(summaries['baseline']['randomized_jitter']['classification_counts'], sort_keys=True)}`",
        f"- Candidate jitter: `{json.dumps(summaries['candidate_minus8']['randomized_jitter']['classification_counts'], sort_keys=True)}`",
        f"- Baseline malformed controls: `{json.dumps(summaries['baseline']['malformed_frames']['classification_counts'], sort_keys=True)}`",
        f"- Candidate malformed controls: `{json.dumps(summaries['candidate_minus8']['malformed_frames']['classification_counts'], sort_keys=True)}`", "",
        "## Minimized counterexample", "",
        f"- Baseline: `{summaries['baseline']['minimized_counterexample']}`",
        f"- Candidate: `{summaries['candidate_minus8']['minimized_counterexample']}`", "",
        "## Full classification transition table", "",
        "| Baseline classification | Candidate classification | Cases |", "|---|---|---:|",
    ]
    for (a, b), n in sorted(transitions.items()):
        md.append(f"| {a} | {b} | {n} |")
    md.extend(["", "## Decision", "", s["promotion_recommendation"], "", f"Production RTL SHA-256: `{after['production_rtl_sha256']}`", f"Production firmware SHA-256: `{after['production_firmware_sha256']}`", ""])
    md_path.write_text("\n".join(md))
    print("===== PAIRED A/B SUMMARY =====", flush=True)
    print(json.dumps({k: v for k, v in s.items() if k not in ("baseline", "candidate_minus8")}, indent=2), flush=True)
    print("BASELINE KEY METRICS:", json.dumps({k: summaries["baseline"][k] for k in ["classification_counts_all_cases", "uniform_period_matrix", "randomized_jitter", "malformed_frames", "minimized_counterexample"]}, indent=2), flush=True)
    print("CANDIDATE KEY METRICS:", json.dumps({k: summaries["candidate_minus8"][k] for k in ["classification_counts_all_cases", "uniform_period_matrix", "randomized_jitter", "malformed_frames", "minimized_counterexample"]}, indent=2), flush=True)
    print("PAIRED DELTA:", json.dumps(s["paired_delta_candidate_minus_baseline"], indent=2), flush=True)
    print(f"JSON REPORT: {json_path}", flush=True)
    print(f"MARKDOWN REPORT: {md_path}", flush=True)
    print(f"RUN DIRECTORY: {RUN_DIR}", flush=True)
    print(f"PRODUCTION RTL SHA256 AFTER: {after['production_rtl_sha256']}", flush=True)
    if not gate_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
