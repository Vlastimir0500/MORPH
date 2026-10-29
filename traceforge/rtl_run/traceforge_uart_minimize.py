import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "traceforge" / "reports"

sys.path.insert(0, str(ROOT / "sim"))
sys.path.insert(0, str(WORK))

from morph_isa_model_v2 import MorphISAModelV2
from traceforge_uart_rtl import digest, expected_snapshot, parse_trace

NOMINAL = 436
IDLE = 10
TAIL = 240


def reverse_byte(value):
    return int(f"{value:08b}"[::-1], 2)


def build_frame(payload, offsets):
    durations = [NOMINAL + offset for offset in offsets]
    if len(durations) != 10 or min(durations) <= 0:
        raise ValueError("Expected ten positive symbol durations")

    trace = [1] * IDLE
    trace.extend([0] * durations[0])

    for bit in range(8):
        level = (payload >> bit) & 1
        trace.extend([level] * durations[bit + 1])

    trace.extend([1] * durations[9])
    trace.extend([1] * TAIL)
    return trace, durations


def main():
    source_report = REPORT_DIR / "uart_rx_jitter_stress_report.json"
    if not source_report.exists():
        raise SystemExit("Missing v0.6 jitter-stress report.")

    previous = json.loads(source_report.read_text())
    initial = next(
        (
            item for item in previous["cases"]
            if item["classification"] == "silent_misdecode"
        ),
        None
    )
    if initial is None:
        raise SystemExit("No silent misdecode found in the saved stress report.")

    payload = int(initial["payload"], 16)
    original_offsets = list(initial["symbol_offsets_cycles"])
    offsets = original_offsets.copy()
    expected_shift = reverse_byte(payload)

    rtl = ROOT / "rtl" / "morph_engine_v2.sv"
    tb = WORK / "morph_engine_v2_traceforge_tb.sv"
    firmware = ROOT / "protocols" / "v2_uart_rx_a6.hex"

    program = [
        int(line.strip(), 16)
        for line in firmware.read_text().splitlines()
        if line.strip()
    ]

    build_dir = WORK / "obj_dir_counterexample_min"
    compile_result = subprocess.run(
        [
            "verilator", "--binary", "--timing", "-Wno-fatal",
            "--top-module", "morph_engine_v2_diff_tb",
            "--Mdir", str(build_dir), str(rtl), str(tb)
        ],
        cwd=ROOT, capture_output=True, text=True, timeout=180
    )
    if compile_result.returncode:
        raise RuntimeError(
            compile_result.stdout + "\n" + compile_result.stderr
        )

    executable = build_dir / "Vmorph_engine_v2_diff_tb"
    program_file = WORK / "morph_v2_program.hex"
    vector_file = WORK / "morph_v2_vectors.hex"

    program_file.write_text(
        "".join(f"{word:04x}\n" for word in program + [0] * (64 - len(program)))
    )

    evaluations = 0
    mismatch_observations = []

    def evaluate(candidate):
        nonlocal evaluations
        evaluations += 1

        pins, durations = build_frame(payload, candidate)
        vector_file.write_text("".join(f"{pin:02x}\n" for pin in pins))

        model = MorphISAModelV2()
        model.load_program(program)
        expected = [expected_snapshot(model.step(rst_n=False, pin_in=0))]
        expected.extend(
            expected_snapshot(model.step(pin_in=pin)) for pin in pins
        )

        run = subprocess.run(
            [str(executable), f"+N={len(pins)}"],
            cwd=ROOT, capture_output=True, text=True, timeout=120
        )
        if run.returncode:
            raise RuntimeError(
                "Counterexample simulation failed:\n"
                + run.stdout[-3000:] + "\n" + run.stderr[-3000:]
            )

        actual = parse_trace(run.stdout)
        mismatch = None

        if len(actual) != len(expected):
            mismatch = {
                "kind": "trace_length",
                "rtl_cycles": len(actual),
                "model_cycles": len(expected)
            }
        else:
            for index, (got, want) in enumerate(zip(actual, expected)):
                if got != want:
                    mismatch = {
                        "kind": "cycle_mismatch",
                        "trace_index": index,
                        "rtl": list(got),
                        "model": list(want)
                    }
                    break

        if not actual:
            raise RuntimeError("Empty RTL trace")

        final = actual[-1]
        pin_out = final[3]
        pin_oe = final[4]
        observed_shift = final[6]
        error_flag = bool((pin_out & pin_oe) & 0x80)
        core_fault = bool(final[9])

        if mismatch:
            classification = "rtl_model_mismatch"
            mismatch_observations.append(mismatch)
        elif error_flag:
            classification = "error_flagged"
        elif core_fault:
            classification = "core_fault"
        elif observed_shift != expected_shift:
            classification = "silent_misdecode"
        else:
            classification = "correct_decode"

        return {
            "offsets": candidate.copy(),
            "durations": durations,
            "input_cycles": len(pins),
            "rtl_model_match": mismatch is None,
            "first_mismatch": mismatch,
            "observed_shift_register": f"0x{observed_shift:02X}",
            "expected_shift_register": f"0x{expected_shift:02X}",
            "error_flag_pin7": error_flag,
            "core_fault": core_fault,
            "classification": classification
        }

    def preserves_silent_failure(result):
        return (
            result["classification"] == "silent_misdecode"
            and result["rtl_model_match"]
        )

    baseline = evaluate(offsets)
    if not preserves_silent_failure(baseline):
        raise SystemExit(
            "Saved failure could not be reproduced. "
            f"Observed classification: {baseline['classification']}"
        )

    current = baseline

    while True:
        changed = False

        for index in range(len(offsets)):
            if offsets[index] == 0:
                continue

            candidate = offsets.copy()
            candidate[index] = 0
            result = evaluate(candidate)

            if preserves_silent_failure(result):
                offsets = candidate
                current = result
                changed = True

        for step in (32, 16, 8, 4, 2, 1):
            for index in range(len(offsets)):
                while abs(offsets[index]) >= step:
                    candidate = offsets.copy()
                    direction = 1 if candidate[index] > 0 else -1
                    candidate[index] -= direction * step

                    result = evaluate(candidate)
                    if preserves_silent_failure(result):
                        offsets = candidate
                        current = result
                        changed = True
                    else:
                        break

        if not changed:
            break

    final_result = evaluate(offsets)
    if not preserves_silent_failure(final_result):
        raise RuntimeError("Final minimized waveform failed reproduction.")

    local_checks = []
    for index, value in enumerate(offsets):
        if value == 0:
            continue

        for candidate_value in (0, value - (1 if value > 0 else -1)):
            candidate = offsets.copy()
            candidate[index] = candidate_value
            result = evaluate(candidate)

            local_checks.append({
                "symbol_index": index,
                "candidate_offset": candidate_value,
                "still_silent_misdecode": preserves_silent_failure(result)
            })

    reducible = any(item["still_silent_misdecode"] for item in local_checks)

    report = {
        "tool": "TRACEFORGE",
        "version": "0.7.0",
        "experiment": "Greedy local minimization of a silent UART misdecode",
        "source_failure": {
            "stress_report": str(source_report.relative_to(ROOT)),
            "amplitude_cycles": initial["amplitude_cycles"],
            "payload": initial["payload"],
            "trial": initial["trial"],
            "seed": initial["seed"],
            "original_classification": initial["classification"]
        },
        "parameters": {
            "nominal_symbol_duration_cycles": NOMINAL,
            "minimization_strategy": (
                "Greedily zero individual symbol offsets, then reduce "
                "absolute offsets using descending step sizes; repeat until stable."
            )
        },
        "original": baseline,
        "minimized": final_result,
        "minimization_summary": {
            "rtl_simulation_evaluations": evaluations,
            "original_nonzero_offsets": sum(value != 0 for value in original_offsets),
            "minimized_nonzero_offsets": sum(value != 0 for value in offsets),
            "original_absolute_offset_sum": sum(abs(value) for value in original_offsets),
            "minimized_absolute_offset_sum": sum(abs(value) for value in offsets),
            "local_reduction_checks": len(local_checks),
            "any_single_coordinate_reduction_still_fails": reducible,
            "locally_minimized_under_tested_operations": not reducible
        },
        "source_hashes": {
            "production_rtl_sha256": digest(rtl),
            "uart_rx_hex_sha256": digest(firmware),
            "isolated_testbench_sha256": digest(tb)
        },
        "local_reduction_checks": local_checks
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "uart_rx_minimized_counterexample.json"
    md_path = REPORT_DIR / "uart_rx_minimized_counterexample.md"
    vector_path = REPORT_DIR / "uart_rx_minimized_counterexample_vectors.hex"

    pins, _ = build_frame(payload, offsets)
    vector_path.write_text("".join(f"{pin:02x}\n" for pin in pins))
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# TRACEFORGE v0.7 — Minimized UART Counterexample",
        "",
        f"- Source failure seed: `{initial['seed']}`",
        f"- Payload: `{payload:#04x}`",
        f"- Original offsets: `{original_offsets}`",
        f"- Minimized offsets: `{offsets}`",
        f"- Original absolute offset sum: {sum(abs(x) for x in original_offsets)}",
        f"- Minimized absolute offset sum: {sum(abs(x) for x in offsets)}",
        f"- Nonzero offsets: {sum(x != 0 for x in original_offsets)} → {sum(x != 0 for x in offsets)}",
        f"- RTL/reference model match: {final_result['rtl_model_match']}",
        f"- Observed shift register: {final_result['observed_shift_register']}",
        f"- Expected shift register: {final_result['expected_shift_register']}",
        f"- Error flag: {final_result['error_flag_pin7']}",
        f"- Core fault: {final_result['core_fault']}",
        f"- Final classification: `{final_result['classification']}`",
        f"- RTL simulation evaluations: {evaluations}",
        f"- Local reduction checks: {'PASS' if not reducible else 'additional reduction found'}",
        "",
        "This is a greedy, locally minimized counterexample, not a proof of global minimality.",
        "",
        f"Production RTL SHA-256: `{report['source_hashes']['production_rtl_sha256']}`",
        "",
        f"Waveform vector file: `{vector_path.relative_to(ROOT)}`",
        ""
    ]
    md_path.write_text("\n".join(lines) + "\n")

    print("SOURCE:", report["source_failure"])
    print("ORIGINAL OFFSETS:", original_offsets)
    print("MINIMIZED OFFSETS:", offsets)
    print("MINIMIZATION:", json.dumps(report["minimization_summary"], sort_keys=True))
    print("FINAL RESULT:", json.dumps(final_result, sort_keys=True))
    print("JSON REPORT:", json_path)
    print("MARKDOWN REPORT:", md_path)
    print("WAVEFORM VECTORS:", vector_path)

    if not final_result["rtl_model_match"]:
        raise SystemExit(1)
    if reducible:
        raise SystemExit("Local reduction is still possible; further minimization needed.")


if __name__ == "__main__":
    main()
