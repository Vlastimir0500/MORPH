import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
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
PHASE_SHIFTS = [-8, 0, 8]
PERIODS = range(400, 471)
NOMINAL = 436
IDLE = 10
TAIL = 240
MINIMIZED_DURATIONS = [427, 436, 421, 379, 436, 400, 396, 377, 436, 436]
LOW_DELTAS = list(range(-220, -207))


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


def build_symbol_duration_frame(payload, durations):
    if len(durations) != 10 or min(durations) <= 0:
        raise ValueError("UART frame must have ten positive symbol durations")
    pins = [1] * IDLE
    pins.extend([0] * durations[0])
    for bit in range(8):
        pins.extend([((payload >> bit) & 1)] * durations[bit + 1])
    pins.extend([1] * durations[9])
    pins.extend([1] * TAIL)
    return pins


def build_aggregate_low_frame(delta):
    low_run = 9 * NOMINAL + delta
    if low_run <= 0:
        raise ValueError("Aggregate low run must remain positive")
    return [1] * IDLE + [0] * low_run + [1] * (NOMINAL + TAIL)


def compress_ranges(values):
    values = sorted(set(values))
    if not values:
        return []
    out = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
        else:
            out.append([start, previous])
            start = previous = value
    out.append([start, previous])
    return out


def main():
    originals = {
        "production_rtl_sha256": sha256(RTL),
        "tinytapeout_engine_sha256": sha256(TT_RTL),
        "production_firmware_sha256": sha256(FIRMWARE),
        "source_testbench_sha256": sha256(SOURCE_TB),
    }
    if originals["production_rtl_sha256"] != originals["tinytapeout_engine_sha256"]:
        raise SystemExit("Production RTL and TinyTapeout engine copy differ; refusing to run")

    base_program = [int(line.strip(), 16) for line in FIRMWARE.read_text().splitlines() if line.strip()]
    if len(base_program) != 18 or base_program[4] != 0x30D7 or base_program[5] != 0x30D7:
        raise SystemExit("UART firmware differs from expected v0.1 candidate baseline")

    run_rel = RUN_DIR.relative_to(ROOT).as_posix()
    tb_text = SOURCE_TB.read_text()
    for old, new in {
        "traceforge/rtl_run/morph_v2_program.hex": f"{run_rel}/morph_v2_program.hex",
        "traceforge/rtl_run/morph_v2_vectors.hex": f"{run_rel}/morph_v2_vectors.hex",
    }.items():
        if old not in tb_text:
            raise SystemExit(f"Expected file reference not found in source testbench: {old}")
        tb_text = tb_text.replace(old, new)

    tb_copy = RUN_DIR / "morph_engine_v2_candidate_validation_tb.sv"
    tb_copy.write_text(tb_text)
    program_path = RUN_DIR / "morph_v2_program.hex"
    vector_path = RUN_DIR / "morph_v2_vectors.hex"
    build_dir = RUN_DIR / "obj_dir"

    compile_cmd = ["verilator", "--binary", "--timing", "-Wno-fatal", "--top-module", "morph_engine_v2_diff_tb", "--Mdir", str(build_dir), str(RTL), str(tb_copy)]
    compilation = subprocess.run(compile_cmd, cwd=ROOT, capture_output=True, text=True, timeout=240)
    (RUN_DIR / "verilator_build.log").write_text(compilation.stdout + "\n" + compilation.stderr)
    if compilation.returncode:
        raise RuntimeError("Verilator compile failed; inspect verilator_build.log")
    executable = build_dir / "Vmorph_engine_v2_diff_tb"

    programs = {}
    for shift in PHASE_SHIFTS:
        candidate = base_program.copy()
        wait_value = 215 + shift // 2
        candidate[4] = 0x3000 | wait_value
        candidate[5] = 0x3000 | wait_value
        programs[shift] = (candidate, wait_value)

    def simulate_case(shift, candidate_program, wait_value, case_name, payload, pins, category, details):
        program_path.write_text("".join(f"{word:04x}\n" for word in candidate_program + [0] * (64 - len(candidate_program))))
        vector_path.write_text("".join(f"{pin:02x}\n" for pin in pins))
        model = MorphISAModelV2()
        model.load_program(candidate_program)
        expected = [expected_snapshot(model.step(rst_n=False, pin_in=0))]
        expected.extend(expected_snapshot(model.step(pin_in=pin)) for pin in pins)
        run = subprocess.run([str(executable), f"+N={len(pins)}"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        if run.returncode:
            raise RuntimeError(f"Simulation failed for {case_name}, phase {shift}:\n{run.stdout[-3000:]}\n{run.stderr[-3000:]}")
        actual = parse_trace(run.stdout)
        mismatch = None
        if len(actual) != len(expected):
            mismatch = {"kind": "trace_length", "rtl_cycles": len(actual), "model_cycles": len(expected)}
        else:
            for index, (got, want) in enumerate(zip(actual, expected)):
                if got != want:
                    mismatch = {"kind": "cycle_mismatch", "index": index, "rtl": list(got), "model": list(want)}
                    break
        if not actual:
            raise RuntimeError(f"Empty trace for {case_name}")
        final = actual[-1]
        pin_out, pin_oe, observed = final[3], final[4], final[6]
        error_flag = bool((pin_out & pin_oe) & 0x80)
        core_fault = bool(final[9])
        expected_shift = reverse_byte(payload)
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
            "candidate_phase_shift_cycles": shift,
            "pre_data_wait_value_each": wait_value,
            "case": case_name,
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

    all_results = []
    total = len(PHASE_SHIFTS) * (len(PAYLOADS) + 1 + len(LOW_DELTAS))
    index = 0
    print("===== UART CANDIDATE VALIDATION v0.1 =====", flush=True)
    print(f"Run directory: {RUN_DIR}", flush=True)
    print(f"Candidate phase shifts: {PHASE_SHIFTS}", flush=True)
    print(f"Cases: {total} across nominal payloads, minimized counterexample, and aggregate low-run boundary", flush=True)

    for shift in PHASE_SHIFTS:
        candidate_program, wait_value = programs[shift]
        for payload in PAYLOADS:
            result = simulate_case(shift, candidate_program, wait_value, f"nominal_{payload:02X}", payload, build_uniform_frame(payload, NOMINAL), "nominal_payload", {"bit_period_cycles": NOMINAL})
            index += 1
        result = simulate_case(shift, candidate_program, wait_value, "minimized_counterexample", 0x00, build_symbol_duration_frame(0x00, MINIMIZED_DURATIONS), "minimized_counterexample", {"symbol_durations_cycles": MINIMIZED_DURATIONS, "low_run_cycles": sum(MINIMIZED_DURATIONS[:9])})
        index += 1
        for delta in LOW_DELTAS:
            result = simulate_case(shift, candidate_program, wait_value, f"aggregate_low_delta_{delta:+d}", 0x00, build_aggregate_low_frame(delta), "aggregate_low_boundary", {"low_run_delta_cycles": delta, "low_run_cycles": 9 * NOMINAL + delta})
            index += 1
        print(f"Phase {shift:+d}: nominal payloads complete; minimized counterexample={result['classification'] if result['case']=='minimized_counterexample' else 'see report'}", flush=True)

    grouped = {}
    for shift in PHASE_SHIFTS:
        selected = [item for item in all_results if item["candidate_phase_shift_cycles"] == shift]
        counts = Counter(item["classification"] for item in selected)
        minimized = next(item for item in selected if item["category"] == "minimized_counterexample")
        boundary = [item for item in selected if item["category"] == "aggregate_low_boundary"]
        transitions = []
        for a, b in zip(boundary, boundary[1:]):
            if a["classification"] != b["classification"]:
                transitions.append({"from_delta": a["low_run_delta_cycles"], "from_classification": a["classification"], "to_delta": b["low_run_delta_cycles"], "to_classification": b["classification"]})
        grouped[str(shift)] = {
            "total_cases": len(selected),
            "classification_counts": dict(sorted(counts.items())),
            "rtl_model_mismatches": counts.get("rtl_model_mismatch", 0),
            "nominal_payload_cases_all_correct": all(item["classification"] == "correct_decode" for item in selected if item["category"] == "nominal_payload"),
            "minimized_counterexample_classification": minimized["classification"],
            "minimized_counterexample_observed": minimized["observed_shift_register"],
            "minimized_counterexample_error_flagged": minimized["error_flag_pin7"],
            "aggregate_low_run_transitions": transitions,
            "aggregate_low_run_classification_segments": classify_segments(boundary),
        }

    after = {
        "production_rtl_sha256": sha256(RTL),
        "tinytapeout_engine_sha256": sha256(TT_RTL),
        "production_firmware_sha256": sha256(FIRMWARE),
    }
    unchanged = all(after[key] == originals[key] for key in after)
    mismatch_count = sum(not item["rtl_model_match"] for item in all_results)
    all_nominal_correct = all(item["classification"] == "correct_decode" for item in all_results if item["category"] == "nominal_payload")
    report = {
        "tool": "TRACEFORGE",
        "version": "0.1.0",
        "experiment": "Validate receive-program phase candidates against nominal frames and known UART failure",
        "parameters": {"phase_shifts_cycles": PHASE_SHIFTS, "nominal_period_cycles": NOMINAL, "payloads": [f"0x{x:02X}" for x in PAYLOADS], "aggregate_low_run_deltas_cycles": LOW_DELTAS, "minimized_symbol_durations_cycles": MINIMIZED_DURATIONS},
        "source_hashes_before": originals,
        "source_hashes_after": after,
        "summary": {"status": "PASS" if mismatch_count == 0 and unchanged and all_nominal_correct else "FAIL", "total_cases": len(all_results), "rtl_model_mismatches": mismatch_count, "production_sources_unchanged": unchanged, "all_nominal_payloads_correct": all_nominal_correct, "candidate_summaries": grouped},
        "cases": all_results,
        "limitations": ["The experiment validates simulated behavior only.", "The aggregate low-run sweep is specific to payload 0x00 and the tested interval range.", "A candidate is not promoted to production firmware by this experiment."]
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stem = RUN_DIR.name
    json_path = REPORT_DIR / f"{stem}.json"
    md_path = REPORT_DIR / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    md = ["# TRACEFORGE â€” UART Candidate Validation v0.1", "", f"- Status: **{report['summary']['status']}**", f"- Cases: {len(all_results)}", f"- RTL/reference-model mismatches: {mismatch_count}", f"- Production RTL/firmware unchanged: {unchanged}", "", "## Candidate summary", "", "| Phase shift | Correct | Silent misdecode | Error flagged | Core fault | RTL/model mismatch | Minimized counterexample |", "|---:|---:|---:|---:|---:|---:|---|"]
    for shift in PHASE_SHIFTS:
        s = grouped[str(shift)]
        c = s["classification_counts"]
        md.append(f"| {shift:+d} | {c.get('correct_decode', 0)} | {c.get('silent_misdecode', 0)} | {c.get('error_flagged', 0)} | {c.get('core_fault', 0)} | {s['rtl_model_mismatches']} | {s['minimized_counterexample_classification']} |")
    md.extend(["", "## Aggregate low-run boundary", ""])
    for shift in PHASE_SHIFTS:
        md.append(f"### Phase shift {shift:+d} cycles")
        for segment in grouped[str(shift)]["aggregate_low_run_classification_segments"]:
            md.append(f"- {segment['classification']}: delta {segment['delta_start_cycles']} through {segment['delta_end_cycles']} cycles")
        md.append("")
    md.extend(["## Interpretation", "", "This report compares isolated candidate firmware variants only. A candidate remains experimental until the complete regression, evidence contracts, and independent boundary tests validate its behavior.", "", f"Production RTL SHA-256: `{after['production_rtl_sha256']}`", f"Production firmware SHA-256: `{after['production_firmware_sha256']}`", ""])
    md_path.write_text("\n".join(md))

    print("===== CANDIDATE VALIDATION SUMMARY =====", flush=True)
    print(json.dumps(report["summary"], indent=2), flush=True)
    print(f"JSON REPORT: {json_path}", flush=True)
    print(f"MARKDOWN REPORT: {md_path}", flush=True)
    print(f"RUN DIRECTORY: {RUN_DIR}", flush=True)
    print(f"PRODUCTION RTL SHA256 AFTER: {after['production_rtl_sha256']}", flush=True)
    if report["summary"]["status"] != "PASS":
        raise SystemExit(1)


def classify_segments(items):
    out = []
    if not items:
        return out
    start = previous = items[0]["low_run_delta_cycles"]
    current = items[0]["classification"]
    for item in items[1:]:
        delta = item["low_run_delta_cycles"]
        classification = item["classification"]
        if delta == previous + 1 and classification == current:
            previous = delta
            continue
        out.append({"classification": current, "delta_start_cycles": start, "delta_end_cycles": previous, "case_count": previous - start + 1})
        start = previous = delta
        current = classification
    out.append({"classification": current, "delta_start_cycles": start, "delta_end_cycles": previous, "case_count": previous - start + 1})
    return out

if __name__ == "__main__":
    main()
