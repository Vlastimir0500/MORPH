import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(__file__).resolve().parent / "reports"
BIT_PERIOD = 436
IDLE_CYCLES = 10
TAIL_CYCLES = 240
PAYLOAD = 0xA6


def build_frame(payload, bit_period=BIT_PERIOD):
    if not 0 <= payload <= 255:
        raise ValueError("payload must be one byte")
    if bit_period < 2:
        raise ValueError("bit_period must be at least two cycles")

    cycles = [1] * IDLE_CYCLES
    cycles.extend([0] * bit_period)

    for bit_index in range(8):
        bit_value = (payload >> bit_index) & 1
        cycles.extend([bit_value] * bit_period)

    cycles.extend([1] * bit_period)
    cycles.extend([1] * TAIL_CYCLES)
    return cycles


def mutate_bad_start(cycles):
    result = cycles.copy()
    start = IDLE_CYCLES
    result[start:start + BIT_PERIOD] = [1] * BIT_PERIOD
    return result


def mutate_bad_stop(cycles):
    result = cycles.copy()
    start = IDLE_CYCLES + 9 * BIT_PERIOD
    result[start:start + BIT_PERIOD] = [0] * BIT_PERIOD
    return result


def mutate_short_start(cycles):
    result = cycles.copy()
    start = IDLE_CYCLES + BIT_PERIOD - 250
    del result[start:start + 250]
    return result


def validate_trace(cycles, bit_period=BIT_PERIOD):
    errors = []
    expected_length = IDLE_CYCLES + 10 * bit_period + TAIL_CYCLES

    if len(cycles) != expected_length:
        errors.append({
            "code": "waveform_length",
            "message": f"Expected {expected_length} cycles, received {len(cycles)}"
        })

    start_position = IDLE_CYCLES + bit_period // 2
    data_positions = [
        IDLE_CYCLES + (index + 1) * bit_period + bit_period // 2
        for index in range(8)
    ]
    stop_position = IDLE_CYCLES + 9 * bit_period + bit_period // 2

    def sample(position, name):
        if position >= len(cycles):
            errors.append({
                "code": "missing_sample",
                "message": f"Cannot sample {name} at cycle {position}"
            })
            return None
        return cycles[position]

    start_bit = sample(start_position, "start")
    data_bits = [sample(position, f"data_{index}")
                 for index, position in enumerate(data_positions)]
    stop_bit = sample(stop_position, "stop")

    if start_bit is not None and start_bit != 0:
        errors.append({
            "code": "start_bit",
            "message": "Start bit must be low at its sampling point"
        })

    for index, value in enumerate(data_bits):
        if value not in (0, 1):
            errors.append({
                "code": "data_sample",
                "message": f"Data bit {index} could not be sampled"
            })

    if stop_bit is not None and stop_bit != 1:
        errors.append({
            "code": "stop_bit",
            "message": "Stop bit must be high at its sampling point"
        })

    decoded = None
    if all(value in (0, 1) for value in data_bits):
        decoded = sum(value << index for index, value in enumerate(data_bits))

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "start_sample": start_bit,
        "data_samples_lsb_first": data_bits,
        "stop_sample": stop_bit,
        "decoded_payload": None if decoded is None else f"0x{decoded:02X}",
        "sample_cycles": {
            "start": start_position,
            "data": data_positions,
            "stop": stop_position
        }
    }


def to_runs(cycles):
    runs = []
    for value in cycles:
        if runs and runs[-1]["level"] == value:
            runs[-1]["cycles"] += 1
        else:
            runs.append({"level": value, "cycles": 1})
    return runs


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_report():
    source = ROOT / "protocols" / "v2_uart_rx_a6.morph"
    firmware = ROOT / "protocols" / "v2_uart_rx_a6.hex"

    baseline = build_frame(PAYLOAD)
    cases = [
        ("valid_a6_frame", baseline, True),
        ("bad_start_stuck_high", mutate_bad_start(baseline), False),
        ("bad_stop_stuck_low", mutate_bad_stop(baseline), False),
        ("start_shortened_by_250_cycles", mutate_short_start(baseline), False),
    ]

    results = []
    for name, cycles, expected_valid in cases:
        observation = validate_trace(cycles)
        passed = observation["valid"] == expected_valid
        results.append({
            "name": name,
            "expected_valid": expected_valid,
            "observed_valid": observation["valid"],
            "expectation_met": passed,
            "cycle_count": len(cycles),
            "observation": observation,
            "waveform_runs": to_runs(cycles)
        })

    report = {
        "tool": "TRACEFORGE",
        "version": "0.1.0",
        "validation_layer": "independent UART waveform contract; no RTL execution",
        "parameters": {
            "payload": f"0x{PAYLOAD:02X}",
            "bit_period_cycles": BIT_PERIOD,
            "idle_cycles": IDLE_CYCLES,
            "tail_cycles": TAIL_CYCLES,
            "data_bits": 8,
            "bit_order": "LSB first",
            "start_level": 0,
            "stop_level": 1
        },
        "source_files": {
            "uart_rx_program": str(source.relative_to(ROOT)),
            "uart_rx_program_sha256": sha256(source),
            "uart_rx_hex": str(firmware.relative_to(ROOT)),
            "uart_rx_hex_sha256": sha256(firmware)
        },
        "summary": {
            "cases": len(results),
            "expectations_met": sum(item["expectation_met"] for item in results),
            "unexpected_results": [
                item["name"] for item in results if not item["expectation_met"]
            ]
        },
        "cases": results
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT / "uart_rx_traceforge_report.json"
    markdown_path = OUTPUT / "uart_rx_traceforge_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# TRACEFORGE UART RX Report",
        "",
        "- Version: 0.1.0",
        "- Payload: `0xA6`",
        f"- Nominal bit period: {BIT_PERIOD} cycles",
        "- Validation: independent waveform contract; RTL not executed",
        f"- Cases meeting expectations: {report['summary']['expectations_met']}/{len(results)}",
        "",
        "| Case | Expected | Observed | Result | Decoded payload |",
        "|---|---|---|---|---|"
    ]

    for item in results:
        obs = item["observation"]
        lines.append(
            f"| {item['name']} | {'valid' if item['expected_valid'] else 'invalid'} "
            f"| {'valid' if item['observed_valid'] else 'invalid'} "
            f"| {'PASS' if item['expectation_met'] else 'FAIL'} "
            f"| {obs['decoded_payload'] or 'N/A'} |"
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "A valid trace must have the expected total length, a low start-bit sample, "
        "eight binary data samples in LSB-first order, and a high stop-bit sample.",
        "The shortened-start mutation is also checked against the nominal frame length.",
        "",
        "This report validates waveform framing only. It does not establish that the "
        "MORPH RTL rejects these mutations or correctly receives the payload.",
        "",
        f"UART source SHA-256: `{report['source_files']['uart_rx_program_sha256']}`",
        f"UART HEX SHA-256: `{report['source_files']['uart_rx_hex_sha256']}`",
        ""
    ])
    markdown_path.write_text("\n".join(lines))

    print(f"Cases meeting expectations: {report['summary']['expectations_met']}/{len(results)}")
    for item in results:
        print(
            f"{'PASS' if item['expectation_met'] else 'FAIL'} "
            f"{item['name']}: valid={item['observation']['valid']} "
            f"errors={[error['code'] for error in item['observation']['errors']]}"
        )
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")

    if report["summary"]["unexpected_results"]:
        raise SystemExit(1)


if __name__ == "__main__":
    generate_report()
