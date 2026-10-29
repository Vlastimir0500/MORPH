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

NOMINAL = 436
MIN_PERIOD = 400
MAX_PERIOD = 470
IDLE_CYCLES = 10
TAIL_CYCLES = 240
PAYLOAD = 0xA6
EXPECTED_SHIFT = 0x65


def build_frame(payload, period):
    trace = [1] * IDLE_CYCLES
    trace.extend([0] * period)
    for bit in range(8):
        trace.extend([((payload >> bit) & 1)] * period)
    trace.extend([1] * period)
    trace.extend([1] * TAIL_CYCLES)
    return trace


def compress_ranges(values):
    if not values:
        return []
    values = sorted(values)
    ranges = []
    start = previous = values[0]
    for value in values[1:]:
        if value != previous + 1:
            ranges.append([start, previous])
            start = value
        previous = value
    ranges.append([start, previous])
    return ranges


def main():
    rtl = ROOT / "rtl" / "morph_engine_v2.sv"
    tb = WORK / "morph_engine_v2_traceforge_tb.sv"
    firmware = ROOT / "protocols" / "v2_uart_rx_a6.hex"

    program = [
        int(line.strip(), 16)
        for line in firmware.read_text().splitlines()
        if line.strip()
    ]

    build_dir = WORK / "obj_dir_timing_sweep"
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
    program_path = WORK / "morph_v2_program.hex"
    vectors_path = WORK / "morph_v2_vectors.hex"
    program_path.write_text(
        "".join(f"{word:04x}\n" for word in program + [0] * (64 - len(program)))
    )

    results = []

    for period in range(MIN_PERIOD, MAX_PERIOD + 1):
        pins = build_frame(PAYLOAD, period)
        vectors_path.write_text("".join(f"{value:02x}\n" for value in pins))

        model = MorphISAModelV2()
        model.load_program(program)
        expected = [expected_snapshot(model.step(rst_n=False, pin_in=0))]
        expected.extend(expected_snapshot(model.step(pin_in=value)) for value in pins)

        run = subprocess.run(
            [str(executable), f"+N={len(pins)}"],
            cwd=ROOT, capture_output=True, text=True, timeout=120
        )
        if run.returncode:
            raise RuntimeError(
                f"Simulation failed at period {period}:\n"
                + run.stdout[-2000:] + "\n" + run.stderr[-2000:]
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

        final = actual[-1] if actual else None
        if final is None:
            raise RuntimeError(f"Empty RTL trace at period {period}")

        shift_reg = final[6]
        pin_out = final[3]
        pin_oe = final[4]
        error_flag = bool((pin_out & pin_oe) & 0x80)
        core_fault = bool(final[9])

        if mismatch:
            classification = "rtl_model_mismatch"
        elif error_flag:
            classification = "error_flagged"
        elif core_fault:
            classification = "core_fault"
        elif shift_reg == EXPECTED_SHIFT:
            classification = "correct_decode"
        else:
            classification = "silent_misdecode"

        results.append({
            "bit_period_cycles": period,
            "offset_from_nominal_cycles": period - NOMINAL,
            "input_trace_cycles": len(pins),
            "rtl_model_match": mismatch is None,
            "first_mismatch": mismatch,
            "shift_register": f"0x{shift_reg:02X}",
            "expected_shift_register": f"0x{EXPECTED_SHIFT:02X}",
            "error_flag_pin7": error_flag,
            "core_fault": core_fault,
            "classification": classification
        })

    counts = Counter(item["classification"] for item in results)
    correct_periods = [
        item["bit_period_cycles"]
        for item in results
        if item["classification"] == "correct_decode"
    ]
    mismatches = [
        item["bit_period_cycles"]
        for item in results
        if not item["rtl_model_match"]
    ]

    report = {
        "tool": "TRACEFORGE",
        "version": "0.3.1",
        "experiment": "UART RX period sweep",
        "parameters": {
            "payload": f"0x{PAYLOAD:02X}",
            "expected_shift_register": f"0x{EXPECTED_SHIFT:02X}",
            "nominal_bit_period_cycles": NOMINAL,
            "tested_period_cycles": [MIN_PERIOD, MAX_PERIOD],
            "period_step_cycles": 1,
            "cases": len(results)
        },
        "source_hashes": {
            "production_rtl_sha256": digest(rtl),
            "uart_rx_hex_sha256": digest(firmware),
            "isolated_testbench_sha256": digest(tb)
        },
        "summary": {
            "classification_counts": dict(sorted(counts.items())),
            "correct_decode_period_ranges": compress_ranges(correct_periods),
            "rtl_model_mismatch_periods": mismatches,
            "all_cycle_comparisons_match": len(mismatches) == 0
        },
        "results": results
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "uart_rx_timing_sweep_report.json"
    md_path = REPORT_DIR / "uart_rx_timing_sweep_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# TRACEFORGE UART RX Timing Sweep",
        "",
        f"- Payload: `0x{PAYLOAD:02X}`",
        f"- Nominal bit period: {NOMINAL} cycles",
        f"- Swept periods: {MIN_PERIOD}–{MAX_PERIOD} cycles, step 1",
        f"- Cases: {len(results)}",
        f"- Cycle-by-cycle RTL/model mismatches: {len(mismatches)}",
        "",
        "## Classification counts",
        ""
    ]

    for name, count in sorted(counts.items()):
        lines.append(f"- `{name}`: {count}")

    lines.extend([
        "",
        "## Correct-decode period ranges",
        "",
        "Ranges include only periods that decoded the expected byte without an error flag or core fault.",
        ""
    ])

    if correct_periods:
        for lower, upper in compress_ranges(correct_periods):
            lines.append(f"- {lower}–{upper} cycles")
    else:
        lines.append("- No correct-decode periods observed.")

    lines.extend([
        "",
        "## Individual results",
        "",
        "| Period | Shift register | Error flag | Classification | RTL/model match |",
        "|---:|---|---|---|---|"
    ])

    for item in results:
        lines.append(
            f"| {item['bit_period_cycles']} | {item['shift_register']} "
            f"| {item['error_flag_pin7']} | {item['classification']} "
            f"| {item['rtl_model_match']} |"
        )

    lines.extend([
        "",
        "This is an empirical sweep for the tested payload and receiver program. "
        "It is not a universal UART timing guarantee.",
        "",
        f"Production RTL SHA-256: `{report['source_hashes']['production_rtl_sha256']}`",
        ""
    ])
    md_path.write_text("\n".join(lines) + "\n")

    print(f"Timing sweep completed: {len(results)} periods")
    print("CLASSIFICATIONS:", json.dumps(dict(sorted(counts.items())), sort_keys=True))
    print("CORRECT-DECODE RANGES:", compress_ranges(correct_periods))
    print("RTL/MODEL MISMATCH PERIODS:", mismatches)
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")

    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
