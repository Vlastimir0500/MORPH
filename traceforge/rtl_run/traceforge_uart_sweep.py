import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "traceforge" / "reports"

sys.path.insert(0, str(WORK))
from traceforge_uart_rtl import digest, expected_snapshot, parse_trace
from morph_isa_model_v2 import MorphISAModelV2

BIT_PERIOD = 436
IDLE_CYCLES = 10
TAIL_CYCLES = 240
PAYLOADS = [0x00, 0xFF, 0x55, 0x3C, 0x81, 0x7E, 0xA5]


def build_frame(payload, period=BIT_PERIOD):
    cycles = [1] * IDLE_CYCLES
    cycles.extend([0] * period)
    for index in range(8):
        cycles.extend([((payload >> index) & 1)] * period)
    cycles.extend([1] * period)
    cycles.extend([1] * TAIL_CYCLES)
    return cycles


def bad_start_glitch(cycles, period=BIT_PERIOD):
    result = cycles.copy()
    start = IDLE_CYCLES
    result[start:start + period] = [1] * period
    result[start:start + 100] = [0] * 100
    return result


def bad_stop_low(cycles, period=BIT_PERIOD):
    result = cycles.copy()
    start = IDLE_CYCLES + 9 * period
    result[start:start + period] = [0] * period
    return result


def reversed_byte(value):
    return int(f"{value:08b}"[::-1], 2)


def main():
    rtl = ROOT / "rtl" / "morph_engine_v2.sv"
    tb = WORK / "morph_engine_v2_traceforge_tb.sv"
    firmware = ROOT / "protocols" / "v2_uart_rx_a6.hex"

    program = [
        int(line.strip(), 16)
        for line in firmware.read_text().splitlines()
        if line.strip()
    ]
    if len(program) != 18:
        raise RuntimeError(f"Expected 18 UART RX words, found {len(program)}")

    build_dir = WORK / "obj_dir_sweep"
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
    cases = []

    for payload in PAYLOADS:
        cases.append((
            f"payload_{payload:02x}",
            build_frame(payload),
            "valid",
            reversed_byte(payload),
            False
        ))

    base = build_frame(0xA6)
    cases.extend([
        ("bad_start_glitch", bad_start_glitch(base), "error", None, False),
        ("bad_stop_low", bad_stop_low(base), "error", None, False)
    ])

    for period in (416, 426, 431, 441, 446, 456):
        cases.append((
            f"timing_period_{period}",
            build_frame(0xA6, period),
            "exploratory",
            reversed_byte(0xA6),
            False
        ))

    results = []

    for name, pins, kind, expected_shift, _ in cases:
        (WORK / "morph_v2_program.hex").write_text(
            "".join(f"{word:04x}\n" for word in program + [0] * (64 - len(program)))
        )
        (WORK / "morph_v2_vectors.hex").write_text(
            "".join(f"{value:02x}\n" for value in pins)
        )

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
                f"RTL simulation failed for {name}:\n"
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

        final = actual[-1] if actual else None
        decoded = None
        error_flag = None
        core_fault = None

        if final is not None:
            decoded = f"0x{final[6]:02X}"
            error_flag = bool((final[4] & 0x80) and (final[3] & 0x80))
            core_fault = bool(final[9])

        if kind == "valid":
            contract_ok = (
                decoded == f"0x{expected_shift:02X}"
                and not error_flag
                and not core_fault
            )
        elif kind == "error":
            contract_ok = bool(error_flag) and not core_fault
        else:
            contract_ok = None

        diff_ok = mismatch is None
        passed = diff_ok and (contract_ok is not False)

        results.append({
            "case": name,
            "category": kind,
            "input_cycles": len(pins),
            "rtl_model_cycle_match": diff_ok,
            "first_mismatch": mismatch,
            "decoded_shift_register": decoded,
            "error_flag_pin7": error_flag,
            "core_fault": core_fault,
            "expected_shift_register": (
                f"0x{expected_shift:02X}" if expected_shift is not None else None
            ),
            "contract_check": contract_ok,
            "result": "PASS" if passed else "FAIL"
        })

    report = {
        "tool": "TRACEFORGE",
        "version": "0.3.0",
        "scope": (
            "Deterministic UART data and timing sweep; Verilator RTL compared "
            "cycle by cycle with the reference model"
        ),
        "parameters": {
            "nominal_bit_period": BIT_PERIOD,
            "exploratory_bit_periods": [416, 426, 431, 441, 446, 456],
            "payloads": [f"0x{value:02X}" for value in PAYLOADS]
        },
        "source_hashes": {
            "production_rtl_sha256": digest(rtl),
            "uart_rx_hex_sha256": digest(firmware),
            "testbench_sha256": digest(tb)
        },
        "summary": {
            "total": len(results),
            "passed": sum(item["result"] == "PASS" for item in results),
            "failed": [item["case"] for item in results if item["result"] != "PASS"],
            "cycle_mismatches": [
                item["case"] for item in results if not item["rtl_model_cycle_match"]
            ],
            "timing_sweep_is_exploratory": True
        },
        "cases": results
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "uart_rx_sweep_report.json"
    md_path = REPORT_DIR / "uart_rx_sweep_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# TRACEFORGE v0.3 — UART Sweep",
        "",
        f"- Total cases: {len(results)}",
        f"- Passed: {report['summary']['passed']}",
        f"- Failed: {len(report['summary']['failed'])}",
        "- RTL compared cycle by cycle against `MorphISAModelV2`.",
        "- Timing variations are exploratory; their payload results are recorded, not assumed.",
        "",
        "| Case | RTL/model | Decoded | Pin-7 error | Contract | Result |",
        "|---|---|---|---|---|---|"
    ]

    for item in results:
        contract = item["contract_check"]
        lines.append(
            f"| {item['case']} | {item['rtl_model_cycle_match']} "
            f"| {item['decoded_shift_register']} "
            f"| {item['error_flag_pin7']} | "
            f"{'exploratory' if contract is None else contract} "
            f"| {item['result']} |"
        )

    lines.extend([
        "",
        f"Production RTL SHA-256: `{report['source_hashes']['production_rtl_sha256']}`",
        "",
        "Timing sweep results measure this particular receiver implementation. "
        "They are not a general UART tolerance specification."
    ])
    md_path.write_text("\n".join(lines) + "\n")

    print(
        f"TRACEFORGE sweep: {report['summary']['passed']}/"
        f"{report['summary']['total']} cases passed"
    )
    for item in results:
        print(
            f"{item['result']} {item['case']}: "
            f"decoded={item['decoded_shift_register']} "
            f"error_pin7={item['error_flag_pin7']} "
            f"rtl_model_match={item['rtl_model_cycle_match']}"
        )
        if item["first_mismatch"]:
            print("FIRST MISMATCH:", item["first_mismatch"])

    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")

    if report["summary"]["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
