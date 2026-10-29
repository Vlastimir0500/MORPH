import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "traceforge" / "reports"

sys.path.insert(0, str(ROOT / "sim"))
from morph_isa_model_v2 import MorphISAModelV2, STATE_CODES

BIT_PERIOD = 436
IDLE_CYCLES = 10
TAIL_CYCLES = 240
PAYLOAD = 0xA6


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_frame(payload):
    cycles = [1] * IDLE_CYCLES
    cycles.extend([0] * BIT_PERIOD)
    for bit in range(8):
        cycles.extend([((payload >> bit) & 1)] * BIT_PERIOD)
    cycles.extend([1] * BIT_PERIOD)
    cycles.extend([1] * TAIL_CYCLES)
    return cycles


def bad_start_glitch(cycles):
    result = cycles.copy()
    start = IDLE_CYCLES
    result[start:start + BIT_PERIOD] = [1] * BIT_PERIOD
    result[start:start + 100] = [0] * 100
    return result


def bad_stop_low(cycles):
    result = cycles.copy()
    start = IDLE_CYCLES + 9 * BIT_PERIOD
    result[start:start + BIT_PERIOD] = [0] * BIT_PERIOD
    return result


def expected_snapshot(snapshot):
    return (
        STATE_CODES[snapshot.state],
        snapshot.pc,
        snapshot.instruction,
        snapshot.pin_out,
        snapshot.pin_oe,
        snapshot.sample_reg,
        snapshot.shift_reg,
        snapshot.wait_count,
        int(snapshot.timed_out),
        int(snapshot.fault),
    )


def parse_trace(output):
    result = []
    for line in output.splitlines():
        if not line.startswith("TRACE "):
            continue
        fields = line.split()
        result.append((
            int(fields[2]),
            int(fields[3]),
            int(fields[4], 16),
            int(fields[5], 16),
            int(fields[6], 16),
            int(fields[7]),
            int(fields[8], 16),
            int(fields[9]),
            int(fields[10]),
            int(fields[11]),
        ))
    return result


def main():
    verilator = shutil.which("verilator")
    if not verilator:
        raise RuntimeError("verilator was not found after loading the tool environment")

    rtl = ROOT / "rtl" / "morph_engine_v2.sv"
    tb = WORK / "morph_engine_v2_traceforge_tb.sv"
    firmware = ROOT / "protocols" / "v2_uart_rx_a6.hex"
    program = [
        int(line.strip(), 16)
        for line in firmware.read_text().splitlines()
        if line.strip()
    ]
    if len(program) != 18:
        raise RuntimeError(f"Expected 18 UART RX instructions, found {len(program)}")

    build_dir = WORK / "obj_dir"
    build_dir.mkdir(parents=True, exist_ok=True)
    command = [
        verilator, "--binary", "--timing", "-Wno-fatal",
        "--top-module", "morph_engine_v2_diff_tb",
        "--Mdir", str(build_dir),
        str(rtl),
        str(tb),
    ]
    compilation = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=180
    )
    if compilation.returncode:
        raise RuntimeError(
            "Verilator build failed.\n" + compilation.stdout + "\n" + compilation.stderr
        )

    executable = build_dir / "Vmorph_engine_v2_diff_tb"
    valid = build_frame(PAYLOAD)
    cases = [
        ("valid_a6", valid, True),
        ("bad_start_glitch", bad_start_glitch(valid), False),
        ("bad_stop_low", bad_stop_low(valid), False),
    ]

    results = []
    for name, pins, expected_valid in cases:
        program_path = WORK / "morph_v2_program.hex"
        vectors_path = WORK / "morph_v2_vectors.hex"

        program_path.write_text(
            "".join(f"{word:04x}\n" for word in program + [0] * (64 - len(program)))
        )
        vectors_path.write_text("".join(f"{pin:02x}\n" for pin in pins))

        model = MorphISAModelV2()
        model.load_program(program)
        expected = [expected_snapshot(model.step(rst_n=False, pin_in=0))]
        expected.extend(expected_snapshot(model.step(pin_in=pin)) for pin in pins)

        simulation = subprocess.run(
            [str(executable), f"+N={len(pins)}"],
            cwd=ROOT, capture_output=True, text=True, timeout=120
        )
        if simulation.returncode:
            raise RuntimeError(
                f"Simulation failed for {name}.\n"
                + simulation.stdout[-5000:] + "\n" + simulation.stderr[-5000:]
            )

        actual = parse_trace(simulation.stdout)
        mismatch = None
        if len(actual) != len(expected):
            mismatch = {
                "kind": "trace_length",
                "expected": len(expected),
                "actual": len(actual)
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
        output = None
        if final is not None:
            output = {
                "state": final[0],
                "pc": final[1],
                "pin_out": f"0x{final[3]:02X}",
                "pin_oe": f"0x{final[4]:02X}",
                "shift_reg": f"0x{final[6]:02X}",
                "timed_out": bool(final[8]),
                "fault": bool(final[9]),
                "error_flag_pin7": bool(final[4] & 0x80 and final[3] & 0x80)
            }

        if expected_valid:
            contract_ok = (
                output is not None
                and output["shift_reg"] == "0x65"
                and not output["error_flag_pin7"]
                and not output["fault"]
            )
        else:
            contract_ok = (
                output is not None
                and output["error_flag_pin7"]
                and not output["fault"]
            )

        passed = mismatch is None and contract_ok
        results.append({
            "case": name,
            "expect_valid": expected_valid,
            "cycle_by_cycle_rtl_model_match": mismatch is None,
            "first_mismatch": mismatch,
            "final_rtl_observation": output,
            "contract_expectation_met": contract_ok,
            "result": "PASS" if passed else "FAIL",
            "cycles_compared": min(len(actual), len(expected))
        })

    report = {
        "tool": "TRACEFORGE",
        "version": "0.2.0",
        "validation_layer": "Verilator RTL versus reference model plus UART end-state contract",
        "parameters": {
            "payload": "0xA6",
            "bit_period_cycles": BIT_PERIOD,
            "idle_cycles": IDLE_CYCLES,
            "tail_cycles": TAIL_CYCLES
        },
        "sources": {
            "production_rtl_sha256": digest(rtl),
            "differential_testbench_sha256": digest(source_testbench_path()),
            "isolated_testbench_sha256": digest(tb),
            "uart_rx_hex_sha256": digest(firmware)
        },
        "summary": {
            "cases": len(results),
            "passed": sum(item["result"] == "PASS" for item in results),
            "failed": [item["case"] for item in results if item["result"] != "PASS"]
        },
        "cases": results
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "uart_rx_rtl_report.json"
    markdown_path = REPORT_DIR / "uart_rx_rtl_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# TRACEFORGE v0.2 — UART RX RTL Report",
        "",
        "- Design: `morph_engine_v2`",
        "- Reference: `MorphISAModelV2`",
        "- Payload: `0xA6`",
        "- Comparison: cycle-by-cycle state, PC, instruction, pin outputs, shift register, wait counter, timeout and fault",
        f"- Cases passed: {report['summary']['passed']}/{len(results)}",
        "",
        "| Case | RTL/model match | Contract | Result | Final shift register | Error pin 7 |",
        "|---|---|---|---|---|---|"
    ]

    for item in results:
        obs = item["final_rtl_observation"] or {}
        lines.append(
            f"| {item['case']} | {item['cycle_by_cycle_rtl_model_match']} "
            f"| {item['contract_expectation_met']} | {item['result']} "
            f"| {obs.get('shift_reg', 'N/A')} | {obs.get('error_flag_pin7', 'N/A')} |"
        )

    lines.extend([
        "",
        "## Scope",
        "",
        "The UART RX RTL is run in Verilator and compared cycle-by-cycle against the independent reference model.",
        "The final contract checks successful decoding of the valid A6 frame and error-flag pin behavior for the two corrupted frames.",
        "This is simulation evidence, not physical silicon validation.",
        "",
        f"Production RTL SHA-256: `{report['sources']['production_rtl_sha256']}`",
        f"Original differential testbench SHA-256: `{report['sources']['differential_testbench_sha256']}`",
        ""
    ])
    markdown_path.write_text("\n".join(lines) + "\n")

    print(f"TRACEFORGE RTL cases passed: {report['summary']['passed']}/{len(results)}")
    for item in results:
        print(
            f"{item['result']} {item['case']}: "
            f"rtl_model_match={item['cycle_by_cycle_rtl_model_match']} "
            f"contract={item['contract_expectation_met']} "
            f"final={item['final_rtl_observation']}"
        )
        if item["first_mismatch"]:
            print(f"FIRST MISMATCH: {item['first_mismatch']}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")

    if report["summary"]["failed"]:
        raise SystemExit(1)


def source_testbench_path():
    return ROOT / "sim" / "morph_engine_v2_diff_tb.sv"


if __name__ == "__main__":
    main()
