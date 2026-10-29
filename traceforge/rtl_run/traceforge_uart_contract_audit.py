import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "traceforge" / "reports"
CONTRACT_DIR = ROOT / "traceforge" / "contracts"

matrix_path = REPORTS / "uart_rx_payload_timing_matrix.json"
jitter_path = REPORTS / "uart_rx_jitter_report.json"
counterexample_path = REPORTS / "uart_rx_minimized_counterexample.json"

matrix = json.loads(matrix_path.read_text())
jitter = json.loads(jitter_path.read_text())
counterexample = json.loads(counterexample_path.read_text())

payload_data = matrix["per_payload"]
common = payload_data[0]["correct_decode_period_ranges"]

for payload in payload_data[1:]:
    intersections = []
    for left_low, left_high in common:
        for right_low, right_high in payload["correct_decode_period_ranges"]:
            low = max(left_low, right_low)
            high = min(left_high, right_high)
            if low <= high:
                intersections.append([low, high])
    common = intersections

if not common:
    raise SystemExit("No common correct-decode period range across tested payloads.")

cases = matrix["cases"]
supported = [
    item for item in cases
    if any(low <= item["bit_period_cycles"] <= high for low, high in common)
]
unsupported = [
    item for item in cases
    if not any(low <= item["bit_period_cycles"] <= high for low, high in common)
]

violations = [
    {
        "payload": item["payload"],
        "period": item["bit_period_cycles"],
        "classification": item["classification"]
    }
    for item in supported
    if item["classification"] != "correct_decode"
    or not item["rtl_model_match"]
    or item["error_flag_pin7"]
    or item["core_fault"]
]

if violations:
    raise SystemExit(
        "CONTRACT AUDIT FAILED: a measured in-envelope case did not meet "
        + json.dumps(violations[:10])
    )

if any(
    item["classification"] != "correct_decode"
    for item in cases
    if item["bit_period_cycles"] == 436
):
    raise SystemExit("CONTRACT AUDIT FAILED: a nominal-period case did not decode correctly.")

minimized = counterexample["minimized"]
durations = minimized["durations"]
out_of_range_symbols = [
    index for index, duration in enumerate(durations)
    if not any(low <= duration <= high for low, high in common)
]

contract = {
    "name": "MORPH UART RX demonstration contract",
    "version": "0.1.0",
    "status": "empirically measured envelope, not a universal UART specification",
    "nominal_bit_period_cycles": 436,
    "tested_uniform_period_range_cycles": [400, 470],
    "payloads_tested": [item["payload"] for item in payload_data],
    "common_observed_correct_decode_ranges_cycles": common,
    "in_envelope_requirements": [
        "Correct byte in the shift register",
        "No UART error indication on pin 7",
        "No core fault",
        "RTL and reference model match cycle by cycle"
    ],
    "evidence": {
        "uniform_period_cases_in_common_ranges": len(supported),
        "uniform_period_cases_in_common_ranges_passed": len(supported),
        "uniform_period_cases_outside_common_ranges": len(unsupported),
        "payload_timing_matrix_total_cases": len(cases),
        "rtl_model_mismatches_in_matrix": matrix["summary"]["rtl_model_mismatches"],
        "randomized_jitter_cases": jitter["summary"]["total"],
        "randomized_jitter_correct_decodes": jitter["summary"]["counts"].get("correct_decode", 0),
        "randomized_jitter_max_abs_offset_cycles": jitter["parameters"]["jitter_limit_cycles"],
        "randomized_jitter_exhaustive": False
    },
    "minimized_variable_timing_counterexample": {
        "expected_shift_register": minimized["expected_shift_register"],
        "observed_shift_register": minimized["observed_shift_register"],
        "symbol_durations_cycles": durations,
        "symbols_outside_uniform_period_envelope": out_of_range_symbols,
        "classification": minimized["classification"],
        "interpretation": "Exploratory nonuniform timing case; outside the uniform-period contract."
    },
    "limitations": [
        "The period range is measured from a finite payload set and finite sweep.",
        "Randomized per-symbol jitter tests are samples, not exhaustive verification.",
        "Behavior outside the stated uniform-period envelope is exploratory; an error flag is not guaranteed.",
        "This contract does not prove operation on fabricated silicon."
    ]
}

CONTRACT_DIR.mkdir(parents=True, exist_ok=True)
contract_path = CONTRACT_DIR / "uart_rx_contract_v0.1.json"
report_path = REPORTS / "uart_rx_contract_audit.json"
markdown_path = REPORTS / "uart_rx_contract_audit.md"

contract_path.write_text(json.dumps(contract, indent=2) + "\n")

audit = {
    "contract_file": str(contract_path.relative_to(ROOT)),
    "common_uniform_period_ranges_cycles": common,
    "in_envelope_cases": len(supported),
    "in_envelope_passed": len(supported) - len(violations),
    "out_of_envelope_cases": len(unsupported),
    "contract_violations": violations,
    "minimized_counterexample_is_nonuniform": len(set(durations)) > 1,
    "minimized_counterexample_symbols_outside_envelope": out_of_range_symbols,
    "audit_passed": not violations
}
report_path.write_text(json.dumps(audit, indent=2) + "\n")

lines = [
    "# TRACEFORGE — UART Contract Audit",
    "",
    f"- Common measured correct-decode ranges: `{common}` cycles",
    f"- In-envelope matrix cases: {len(supported)}",
    f"- In-envelope cases passed: {len(supported) - len(violations)}",
    f"- Cases outside the envelope: {len(unsupported)}",
    f"- Contract violations: {len(violations)}",
    f"- Minimized nonuniform counterexample symbol durations outside the envelope: {out_of_range_symbols}",
    "",
    "The common period range is based on the tested payload/timing matrix. "
    "It is empirical evidence for this particular receiver demonstration, not a universal UART timing guarantee.",
    "",
    "Cases outside the measured envelope remain exploratory; the contract does not require them to be decoded or flagged.",
    ""
]
markdown_path.write_text("\n".join(lines))

print("===== UART CONTRACT AUDIT =====")
print(json.dumps(audit, indent=2))
print("CONTRACT:", contract_path)
print("REPORT:", report_path)
print("MARKDOWN:", markdown_path)

if violations:
    raise SystemExit(1)
