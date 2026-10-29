import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "traceforge" / "reports"

sys.path.insert(0, str(ROOT / "sim"))
sys.path.insert(0, str(WORK))

from morph_isa_model_v2 import MorphISAModelV2
from traceforge_uart_rtl import digest, expected_snapshot, parse_trace

PAYLOADS = [0x00, 0xFF, 0x55, 0x3C, 0x81, 0x7E, 0xA5, 0xA6]
PERIODS = range(400, 471)
NOMINAL = 436
IDLE = 10
TAIL = 240


def reverse_byte(value):
    return int(f"{value:08b}"[::-1], 2)


def build_frame(payload, period):
    trace = [1] * IDLE
    trace.extend([0] * period)
    for bit in range(8):
        trace.extend([((payload >> bit) & 1)] * period)
    trace.extend([1] * period)
    trace.extend([1] * TAIL)
    return trace


def ranges(values):
    values = sorted(values)
    result = []
    for value in values:
        if not result or value > result[-1][1] + 1:
            result.append([value, value])
        else:
            result[-1][1] = value
    return result


def main():
    rtl = ROOT / "rtl" / "morph_engine_v2.sv"
    original_tb = ROOT / "sim" / "morph_engine_v2_diff_tb.sv"
    tb = WORK / "morph_engine_v2_traceforge_tb.sv"
    firmware = ROOT / "protocols" / "v2_uart_rx_a6.hex"

    program = [
        int(line.strip(), 16)
        for line in firmware.read_text().splitlines()
        if line.strip()
    ]
    if len(program) != 18:
        raise RuntimeError(f"Expected 18 UART RX instructions, got {len(program)}")

    build_dir = WORK / "obj_dir_payload_timing_matrix"
    build = subprocess.run(
        [
            "verilator", "--binary", "--timing", "-Wno-fatal",
            "--top-module", "morph_engine_v2_diff_tb",
            "--Mdir", str(build_dir), str(rtl), str(tb)
        ],
        cwd=ROOT, capture_output=True, text=True, timeout=180
    )
    if build.returncode:
        raise RuntimeError(build.stdout + "\n" + build.stderr)

    executable = build_dir / "Vmorph_engine_v2_diff_tb"
    program_file = WORK / "morph_v2_program.hex"
    vector_file = WORK / "morph_v2_vectors.hex"

    program_file.write_text(
        "".join(f"{word:04x}\n" for word in program + [0] * (64 - len(program)))
    )

    results = []

    for payload in PAYLOADS:
        expected_shift = reverse_byte(payload)

        for period in PERIODS:
            pins = build_frame(payload, period)
            vector_file.write_text("".join(f"{pin:02x}\n" for pin in pins))

            model = MorphISAModelV2()
            model.load_program(program)
            expected = [expected_snapshot(model.step(rst_n=False, pin_in=0))]
            expected.extend(expected_snapshot(model.step(pin_in=pin)) for pin in pins)

            run = subprocess.run(
                [str(executable), f"+N={len(pins)}"],
                cwd=ROOT, capture_output=True, text=True, timeout=120
            )
            if run.returncode:
                raise RuntimeError(
                    f"Simulation failed for payload 0x{payload:02X}, "
                    f"period {period}:\n{run.stdout[-2000:]}\n{run.stderr[-2000:]}"
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
                raise RuntimeError("Simulator returned an empty trace.")

            final = actual[-1]
            pin_out = final[3]
            pin_oe = final[4]
            shift = final[6]
            error_flag = bool((pin_out & pin_oe) & 0x80)
            core_fault = bool(final[9])

            if mismatch:
                classification = "rtl_model_mismatch"
            elif error_flag:
                classification = "error_flagged"
            elif core_fault:
                classification = "core_fault"
            elif shift == expected_shift:
                classification = "correct_decode"
            else:
                classification = "silent_misdecode"

            results.append({
                "payload": f"0x{payload:02X}",
                "bit_period_cycles": period,
                "offset_from_nominal_cycles": period - NOMINAL,
                "rtl_model_match": mismatch is None,
                "first_mismatch": mismatch,
                "expected_shift_register": f"0x{expected_shift:02X}",
                "observed_shift_register": f"0x{shift:02X}",
                "error_flag_pin7": error_flag,
                "core_fault": core_fault,
                "classification": classification
            })

    per_payload = []
    for payload in PAYLOADS:
        subset = [r for r in results if r["payload"] == f"0x{payload:02X}"]
        counts = Counter(r["classification"] for r in subset)
        good = [
            r["bit_period_cycles"]
            for r in subset if r["classification"] == "correct_decode"
        ]
        per_payload.append({
            "payload": f"0x{payload:02X}",
            "tested_periods": len(subset),
            "classification_counts": dict(sorted(counts.items())),
            "correct_decode_period_ranges": ranges(good)
        })

    mismatch_cases = [
        {
            "payload": r["payload"],
            "period": r["bit_period_cycles"],
            "mismatch": r["first_mismatch"]
        }
        for r in results if not r["rtl_model_match"]
    ]

    report = {
        "tool": "TRACEFORGE",
        "version": "0.4.0",
        "experiment": "UART payload-by-period matrix",
        "scope": "Empirical simulation of the existing UART RX program",
        "parameters": {
            "payloads": [f"0x{x:02X}" for x in PAYLOADS],
            "period_range_cycles": [400, 470],
            "period_step_cycles": 1,
            "nominal_period_cycles": NOMINAL,
            "total_cases": len(results)
        },
        "source_hashes": {
            "production_rtl_sha256": digest(rtl),
            "uart_rx_hex_sha256": digest(firmware),
            "original_testbench_sha256": digest(original_tb),
            "isolated_testbench_sha256": digest(tb)
        },
        "summary": {
            "total_cases": len(results),
            "correct_decode": sum(r["classification"] == "correct_decode" for r in results),
            "silent_misdecode": sum(r["classification"] == "silent_misdecode" for r in results),
            "error_flagged": sum(r["classification"] == "error_flagged" for r in results),
            "core_fault": sum(r["classification"] == "core_fault" for r in results),
            "rtl_model_mismatches": len(mismatch_cases)
        },
        "per_payload": per_payload,
        "mismatches": mismatch_cases,
        "cases": results
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "uart_rx_payload_timing_matrix.json"
    md_path = REPORT_DIR / "uart_rx_payload_timing_matrix.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# TRACEFORGE v0.4 — UART Payload/Timing Matrix",
        "",
        f"- Payloads: {len(PAYLOADS)}",
        f"- Bit periods: {len(list(PERIODS))}",
        f"- Total RTL runs: {len(results)}",
        f"- Cycle-by-cycle RTL/model mismatches: {len(mismatch_cases)}",
        "",
        "| Payload | Correct decode ranges (cycles) | Correct | Silent misdecode | Error flagged |",
        "|---|---|---:|---:|---:|"
    ]

    for item in per_payload:
        counts = item["classification_counts"]
        lines.append(
            f"| {item['payload']} | {item['correct_decode_period_ranges']} "
            f"| {counts.get('correct_decode', 0)} "
            f"| {counts.get('silent_misdecode', 0)} "
            f"| {counts.get('error_flagged', 0)} |"
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "Correct-decode ranges are empirical for this receiver program, payload, "
        "clock model and trace generator. Timing results are not a general UART specification.",
        "Silent misdecode means the final shifted byte differs from the expected byte "
        "without the receiver's pin-7 error flag or core fault being asserted.",
        "",
        f"Production RTL SHA-256: `{report['source_hashes']['production_rtl_sha256']}`",
        ""
    ])
    md_path.write_text("\n".join(lines) + "\n")

    print(f"Completed {len(results)} cases.")
    print("SUMMARY:", json.dumps(report["summary"], sort_keys=True))
    for item in per_payload:
        print(
            f"{item['payload']}: ranges={item['correct_decode_period_ranges']} "
            f"counts={item['classification_counts']}"
        )
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")

    if mismatch_cases:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
