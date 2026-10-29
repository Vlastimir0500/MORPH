import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ["MORPH_ROOT"]).resolve()
RUN_DIR = Path(os.environ["MORPH_RUN_DIR"]).resolve()
WORK = ROOT / "traceforge" / "rtl_run"
REPORT_DIR = ROOT / "traceforge" / "reports"
RTL = ROOT / "rtl" / "morph_engine_v2.sv"
TT_RTL = ROOT / "tinytapeout-template-v2" / "src" / "morph_engine.sv"
FIRMWARE = ROOT / "protocols" / "v2_uart_rx_a6.hex"
TB_SOURCE = WORK / "morph_engine_v2_traceforge_tb.sv"

sys.path.insert(0, str(WORK))
sys.path.insert(0, str(ROOT / "sim"))
from traceforge_uart_rtl import expected_snapshot, parse_trace
from morph_isa_model_v2 import MorphISAModelV2

PAYLOADS = [0x00, 0xFF, 0x55, 0x3C, 0x81, 0x7E, 0xA5, 0xA6]
PERIODS = list(range(400, 471))
PHASE_SHIFTS = [-8, 0, 8]
IDLE = 10
TAIL = 240


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reverse_byte(value):
    result = 0
    for bit in range(8):
        result = (result << 1) | ((value >> bit) & 1)
    return result


def build_frame(payload, period):
    pins = [1] * IDLE
    pins.extend([0] * period)
    for bit in range(8):
        pins.extend([((payload >> bit) & 1)] * period)
    pins.extend([1] * period)
    pins.extend([1] * TAIL)
    return pins


def compress_ranges(values):
    if not values:
        return []
    values = sorted(set(values))
    ranges = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append([start, previous])
        start = previous = value
    ranges.append([start, previous])
    return ranges


def classify(program, payload, period, executable, program_path, vector_path):
    pins = build_frame(payload, period)
    program_path.write_text("".join(f"{word:04x}\n" for word in program + [0] * (64 - len(program))))
    vector_path.write_text("".join(f"{pin:02x}\n" for pin in pins))

    model = MorphISAModelV2()
    model.load_program(program)
    expected = [expected_snapshot(model.step(rst_n=False, pin_in=0))]
    expected.extend(expected_snapshot(model.step(pin_in=pin)) for pin in pins)

    run = subprocess.run([str(executable), f"+N={len(pins)}"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    if run.returncode:
        raise RuntimeError(f"Simulation failed for payload=0x{payload:02X}, period={period}:\n{run.stdout[-2500:]}\n{run.stderr[-2500:]}")
    actual = parse_trace(run.stdout)
    mismatch = None
    if len(actual) != len(expected):
        mismatch = {"kind": "trace_length", "rtl": len(actual), "model": len(expected)}
    else:
        for index, (got, want) in enumerate(zip(actual, expected)):
            if got != want:
                mismatch = {"kind": "cycle_mismatch", "index": index, "rtl": list(got), "model": list(want)}
                break
    if not actual:
        raise RuntimeError("Simulator produced no trace records")

    final = actual[-1]
    pin_out, pin_oe, shift_reg = final[3], final[4], final[6]
    error_flag = bool((pin_out & pin_oe) & 0x80)
    core_fault = bool(final[9])
    expected_shift = reverse_byte(payload)
    if mismatch:
        classification = "rtl_model_mismatch"
    elif error_flag:
        classification = "error_flagged"
    elif core_fault:
        classification = "core_fault"
    elif shift_reg != expected_shift:
        classification = "silent_misdecode"
    else:
        classification = "correct_decode"
    return {
        "payload": f"0x{payload:02X}",
        "period_cycles": period,
        "expected_shift_register": f"0x{expected_shift:02X}",
        "observed_shift_register": f"0x{shift_reg:02X}",
        "error_flag_pin7": error_flag,
        "core_fault": core_fault,
        "rtl_model_match": mismatch is None,
        "first_mismatch": mismatch,
        "classification": classification,
    }


def main():
    original_hashes = {"production_rtl_sha256": sha256(RTL), "tiny_tapeout_engine_sha256": sha256(TT_RTL), "production_firmware_sha256": sha256(FIRMWARE), "original_testbench_sha256": sha256(TB_SOURCE)}
    if original_hashes["production_rtl_sha256"] != original_hashes["tiny_tapeout_engine_sha256"]:
        raise SystemExit("Production RTL and TinyTapeout engine copy do not match; refusing experiment")

    base_program = [int(line.strip(), 16) for line in FIRMWARE.read_text().splitlines() if line.strip()]
    if len(base_program) != 18 or base_program[4] != 0x30D7 or base_program[5] != 0x30D7:
        raise SystemExit("UART firmware does not match expected v2.0 wait-instruction baseline")

    run_rel = RUN_DIR.relative_to(ROOT).as_posix()
    tb_text = TB_SOURCE.read_text()
    replacements = {
        "traceforge/rtl_run/morph_v2_program.hex": f"{run_rel}/morph_v2_program.hex",
        "traceforge/rtl_run/morph_v2_vectors.hex": f"{run_rel}/morph_v2_vectors.hex",
    }
    for old, new in replacements.items():
        if old not in tb_text:
            raise SystemExit(f"Expected testbench path not found: {old}")
        tb_text = tb_text.replace(old, new)
    tb_copy = RUN_DIR / "morph_engine_v2_phase_sweep_tb.sv"
    tb_copy.write_text(tb_text)
    program_path = RUN_DIR / "morph_v2_program.hex"
    vector_path = RUN_DIR / "morph_v2_vectors.hex"
    build_dir = RUN_DIR / "obj_dir"

    print("===== UART SAMPLE-PHASE MARGIN SWEEP v0.1 =====", flush=True)
    print(f"Run directory: {RUN_DIR}", flush=True)
    print(f"Production RTL SHA256: {original_hashes['production_rtl_sha256']}", flush=True)
    print(f"Payloads: {[f'0x{x:02X}' for x in PAYLOADS]}", flush=True)
    print(f"Periods: {PERIODS[0]}..{PERIODS[-1]} cycles inclusive", flush=True)
    print(f"Candidate sample-phase shifts: {PHASE_SHIFTS} cycles; implemented by changing both pre-data WAIT instructions equally", flush=True)

    compile_cmd = ["verilator", "--binary", "--timing", "-Wno-fatal", "--top-module", "morph_engine_v2_diff_tb", "--Mdir", str(build_dir), str(RTL), str(tb_copy)]
    compilation = subprocess.run(compile_cmd, cwd=ROOT, capture_output=True, text=True, timeout=240)
    (RUN_DIR / "verilator_build.log").write_text(compilation.stdout + "\n" + compilation.stderr)
    if compilation.returncode:
        raise RuntimeError("Verilator compilation failed; see verilator_build.log")
    executable = build_dir / "Vmorph_engine_v2_diff_tb"

    candidate_results = []
    total = len(PHASE_SHIFTS) * len(PAYLOADS) * len(PERIODS)
    completed = 0
    for shift in PHASE_SHIFTS:
        candidate_program = base_program.copy()
        wait_value = 215 + shift // 2
        candidate_program[4] = 0x3000 | wait_value
        candidate_program[5] = 0x3000 | wait_value
        cases = []
        for payload in PAYLOADS:
            for period in PERIODS:
                result = classify(candidate_program, payload, period, executable, program_path, vector_path)
                result["phase_shift_cycles"] = shift
                result["pre_data_wait_value"] = wait_value
                cases.append(result)
                completed += 1
                if completed % 100 == 0 or completed == total:
                    print(f"Progress: {completed}/{total}; shift={shift:+d}; payload=0x{payload:02X}; period={period}; {result['classification']}", flush=True)

        counts = Counter(item["classification"] for item in cases)
        per_payload = []
        per_payload_correct = {}
        for payload in PAYLOADS:
            selected = [item for item in cases if item["payload"] == f"0x{payload:02X}"]
            correct_periods = [item["period_cycles"] for item in selected if item["classification"] == "correct_decode"]
            per_payload_correct[payload] = set(correct_periods)
            ccounts = Counter(item["classification"] for item in selected)
            per_payload.append({"payload": f"0x{payload:02X}", "classification_counts": dict(sorted(ccounts.items())), "correct_period_ranges_cycles": compress_ranges(correct_periods)})
        common = set(PERIODS)
        for payload in PAYLOADS:
            common &= per_payload_correct[payload]
        candidate_results.append({
            "phase_shift_cycles": shift,
            "pre_data_wait_value_each": wait_value,
            "program_words_4_and_5": [f"0x{candidate_program[4]:04X}", f"0x{candidate_program[5]:04X}"],
            "total_cases": len(cases),
            "classification_counts": dict(sorted(counts.items())),
            "rtl_model_mismatches": counts.get("rtl_model_mismatch", 0),
            "common_correct_period_ranges_cycles": compress_ranges(common),
            "per_payload": per_payload,
            "cases": cases,
        })

    production_hash_after = sha256(RTL)
    tt_hash_after = sha256(TT_RTL)
    firmware_hash_after = sha256(FIRMWARE)
    sources_unchanged = production_hash_after == original_hashes["production_rtl_sha256"] and tt_hash_after == original_hashes["tiny_tapeout_engine_sha256"] and firmware_hash_after == original_hashes["production_firmware_sha256"]
    candidate_mismatches = sum(item["rtl_model_mismatches"] for item in candidate_results)
    all_candidate_runs_passed = candidate_mismatches == 0 and sources_unchanged

    report = {
        "tool": "TRACEFORGE",
        "version": "0.1.0",
        "experiment": "UART RX receive-program sample-phase margin sweep",
        "scope": "Three isolated firmware variants; production RTL and firmware remain unchanged",
        "parameters": {"payloads": [f"0x{x:02X}" for x in PAYLOADS], "period_range_cycles": [PERIODS[0], PERIODS[-1]], "period_step_cycles": 1, "candidate_phase_shifts_cycles": PHASE_SHIFTS, "cases_per_candidate": len(PAYLOADS) * len(PERIODS), "total_cases": total},
        "source_hashes_before": original_hashes,
        "source_hashes_after": {"production_rtl_sha256": production_hash_after, "tiny_tapeout_engine_sha256": tt_hash_after, "production_firmware_sha256": firmware_hash_after},
        "summary": {"status": "PASS" if all_candidate_runs_passed else "FAIL", "total_cases": total, "rtl_model_mismatches": candidate_mismatches, "production_sources_unchanged": sources_unchanged},
        "candidates": candidate_results,
        "limitations": ["This is a simulation experiment using a fixed-period input model.", "The common period ranges are measured only over the listed payloads and tested periods.", "Improvement is not assumed; candidate timing shifts may trade lower- and higher-period margins.", "No production RTL or production firmware was edited."],
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stem = RUN_DIR.name
    json_path = REPORT_DIR / f"{stem}.json"
    md_path = REPORT_DIR / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    md = ["# TRACEFORGE â€” UART Sample-Phase Margin Sweep v0.1", "", f"- Status: **{report['summary']['status']}**", f"- Total simulated cases: {total}", f"- RTL/reference-model mismatches: {candidate_mismatches}", f"- Production RTL and firmware unchanged: {sources_unchanged}", "", "## Candidate results", "", "| Phase shift (cycles) | Wait value per instruction | Correct | Silent misdecode | Error flagged | Core fault | RTL/model mismatch | Common correct period range |", "|---:|---:|---:|---:|---:|---:|---:|---|"]
    for candidate in candidate_results:
        counts = candidate["classification_counts"]
        ranges = ", ".join(f"{a}â€“{b}" for a, b in candidate["common_correct_period_ranges_cycles"]) or "none"
        md.append(f"| {candidate['phase_shift_cycles']:+d} | {candidate['pre_data_wait_value_each']} | {counts.get('correct_decode', 0)} | {counts.get('silent_misdecode', 0)} | {counts.get('error_flagged', 0)} | {counts.get('core_fault', 0)} | {candidate['rtl_model_mismatches']} | {ranges} |")
    md += ["", "## Per-payload measured ranges", ""]
    for candidate in candidate_results:
        md.append(f"### Phase shift {candidate['phase_shift_cycles']:+d} cycles")
        md.append("")
        for entry in candidate["per_payload"]:
            ranges = ", ".join(f"{a}â€“{b}" for a, b in entry["correct_period_ranges_cycles"]) or "none"
            md.append(f"- {entry['payload']}: {ranges} cycles")
        md.append("")
    md += ["## Interpretation", "", "Use the measured common ranges to determine whether retiming improves tolerance or merely shifts the trade-off. Any candidate is experimental firmware only; no production source was modified.", "", f"Production RTL SHA-256: `{production_hash_after}`", f"Production firmware SHA-256: `{firmware_hash_after}`", ""]
    md_path.write_text("\n".join(md))

    print("===== SAMPLE-PHASE SWEEP SUMMARY =====", flush=True)
    print(json.dumps(report["summary"], indent=2), flush=True)
    for candidate in candidate_results:
        print(json.dumps({k: candidate[k] for k in ("phase_shift_cycles", "pre_data_wait_value_each", "classification_counts", "rtl_model_mismatches", "common_correct_period_ranges_cycles")}, sort_keys=True), flush=True)
    print(f"JSON REPORT: {json_path}", flush=True)
    print(f"MARKDOWN REPORT: {md_path}", flush=True)
    print(f"RUN DIRECTORY: {RUN_DIR}", flush=True)
    print(f"PRODUCTION RTL SHA256 AFTER: {production_hash_after}", flush=True)
    if not all_candidate_runs_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
