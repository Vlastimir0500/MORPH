from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / "MORPH"
REPORT_DIR = ROOT / "traceforge" / "reports"
CONTRACT_PATH = ROOT / "traceforge" / "contracts" / "uart_rx_evidence_v0.1.json"
TIMING_CONTRACT_PATH = ROOT / "traceforge" / "contracts" / "uart_rx_contract_v0.1.json"
MATRIX_PATH = REPORT_DIR / "uart_rx_payload_timing_matrix.json"
TIMING_AUDIT_PATH = REPORT_DIR / "uart_rx_contract_audit.json"
REPLAY_PATH = REPORT_DIR / "uart_rx_counterexample_replay_report.json"
EVIDENCE_AUDIT_PATH = REPORT_DIR / "uart_rx_evidence_v0_1.audit.json"
RTL_PATH = ROOT / "rtl" / "morph_engine_v2.sv"
OUT_JSON = REPORT_DIR / "uart_negative_controls_v0.1.json"
OUT_MD = REPORT_DIR / "uart_negative_controls_v0.1.md"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"Required evidence file is missing: {path}")
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def expected_rtl_hash(contract: dict) -> str:
    for check in contract.get("checks", []):
        if check.get("id") == "production_rtl_matches_evidence_revision":
            return str(check.get("expected", ""))
    raise ValueError("UART evidence contract lacks production_rtl_matches_evidence_revision")


def validate_bundle(bundle: dict, contract: dict, timing_contract: dict, contract_sha256: str, actual_rtl_sha256: str) -> list[str]:
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    expected_hash = expected_rtl_hash(contract)
    require(bool(expected_hash), "contract has an empty expected production RTL hash")
    require(actual_rtl_sha256 == expected_hash, "production RTL hash differs from the evidence contract")

    matrix = bundle.get("matrix") if isinstance(bundle.get("matrix"), dict) else {}
    matrix_hash = matrix.get("source_hashes", {}).get("production_rtl_sha256")
    require(matrix_hash == actual_rtl_sha256, "timing matrix production RTL hash is stale")
    summary = matrix.get("summary", {}) if isinstance(matrix.get("summary"), dict) else {}
    require(summary.get("rtl_model_mismatches") == 0, "timing matrix records RTL/reference-model mismatches")

    cases = matrix.get("cases", [])
    require(isinstance(cases, list) and len(cases) > 0, "timing matrix has no case list")
    limits = timing_contract.get("common_observed_correct_decode_ranges_cycles", [])
    valid_ranges = [item for item in limits if isinstance(item, list) and len(item) == 2]
    require(bool(valid_ranges), "UART contract has no usable observed timing range")
    envelope_cases = []
    for case in cases if isinstance(cases, list) else []:
        if not isinstance(case, dict):
            continue
        period = case.get("bit_period_cycles")
        if isinstance(period, int) and any(lo <= period <= hi for lo, hi in valid_ranges):
            envelope_cases.append(case)

    def correct_in_envelope(case: dict) -> bool:
        return (
            case.get("classification") == "correct_decode"
            and case.get("rtl_model_match") is True
            and case.get("error_flag_pin7") is False
            and case.get("core_fault") is False
        )

    bad_envelope_cases = sum(not correct_in_envelope(case) for case in envelope_cases)
    audit = bundle.get("timing_audit") if isinstance(bundle.get("timing_audit"), dict) else {}
    require(len(envelope_cases) == 384, f"expected 384 in-envelope cases; found {len(envelope_cases)}")
    require(bad_envelope_cases == 0, f"{bad_envelope_cases} in-envelope cases violate the UART evidence contract")
    require(audit.get("in_envelope_cases") == len(envelope_cases), "timing audit in-envelope count disagrees with the matrix")
    require(audit.get("in_envelope_passed") == len(envelope_cases) - bad_envelope_cases, "timing audit pass count disagrees with the matrix")
    require(audit.get("audit_passed") is True, "UART timing contract audit is not marked PASS")
    require(audit.get("contract_violations") == [], "UART timing contract audit reports violations")
    require(audit.get("common_uniform_period_ranges_cycles") == limits, "timing audit and evidence contract disagree on the measured envelope")

    nominal = [case for case in cases if isinstance(case, dict) and case.get("bit_period_cycles") == timing_contract.get("nominal_bit_period_cycles")] if isinstance(cases, list) else []
    require(len(nominal) >= 8, f"expected at least 8 nominal-period payload cases; found {len(nominal)}")
    require(all(correct_in_envelope(case) for case in nominal), "one or more nominal-period UART cases fail")

    replay = bundle.get("replay") if isinstance(bundle.get("replay"), dict) else {}
    require(replay.get("production_rtl_sha256") == actual_rtl_sha256, "counterexample replay uses a stale production RTL hash")
    require(replay.get("replay_passed") is True, "counterexample replay did not pass")
    require(replay.get("silent_misdecode_reproduced") is True, "known silent UART misdecode was not reproduced")
    require(replay.get("rtl_reference_model_cycle_match") is True, "counterexample replay reports an RTL/model mismatch")
    require(replay.get("saved_waveform_matches_reconstruction") is True, "saved UART counterexample waveform is not reproducible")
    require(replay.get("payload") == "0x00", "counterexample payload differs from the recorded case")
    require(replay.get("expected_shift_register") == "0x00", "counterexample expected shift-register value changed")
    require(replay.get("observed_shift_register") == "0x01", "counterexample observed shift-register value changed")
    require(replay.get("error_flag_pin7") is False and replay.get("core_fault") is False, "counterexample no longer represents a silent misdecode")

    evidence_audit = bundle.get("evidence_audit") if isinstance(bundle.get("evidence_audit"), dict) else {}
    require(evidence_audit.get("status") == "PASS", "UART evidence-contract audit status is not PASS")
    require(evidence_audit.get("contract_sha256") == contract_sha256, "UART evidence audit contract hash is stale")
    check_rows = evidence_audit.get("checks", [])
    passed = evidence_audit.get("checks_passed")
    total = evidence_audit.get("checks_total")
    require(isinstance(check_rows, list) and len(check_rows) > 0, "UART evidence audit has no individual check records")
    require(isinstance(passed, int) and isinstance(total, int) and passed == total == len(check_rows), "UART evidence audit check counts are inconsistent")
    require(all(isinstance(item, dict) and item.get("passed") is True for item in check_rows), "one or more UART evidence audit checks failed")
    return errors


def mutate_case(bundle: dict, predicate, key: str, value) -> None:
    for case in bundle["matrix"]["cases"]:
        if predicate(case):
            case[key] = value
            return
    raise ValueError(f"Could not find a matrix case to mutate: {key}")


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    timing_contract = load_json(TIMING_CONTRACT_PATH)
    contract_hash = sha256_file(CONTRACT_PATH)
    actual_rtl_hash = sha256_file(RTL_PATH)
    base = {
        "matrix": load_json(MATRIX_PATH),
        "timing_audit": load_json(TIMING_AUDIT_PATH),
        "replay": load_json(REPLAY_PATH),
        "evidence_audit": load_json(EVIDENCE_AUDIT_PATH),
    }

    scenarios = []

    def run_scenario(name: str, expected: str, data: dict, expected_reason: str | None = None) -> None:
        errors = validate_bundle(data, contract, timing_contract, contract_hash, actual_rtl_hash)
        if expected == "PASS":
            passed = not errors
            detected = errors
        else:
            passed = bool(errors) and (expected_reason is None or any(expected_reason in error for error in errors))
            detected = errors
        scenarios.append({
            "scenario": name,
            "expected": expected,
            "observed": "PASS" if not errors else "REJECTED",
            "test_passed": passed,
            "detected": detected,
        })

    run_scenario("clean_baseline", "PASS", copy.deepcopy(base))

    data = copy.deepcopy(base)
    mutate_case(data, lambda c: c.get("bit_period_cycles") == 436, "classification", "silent_misdecode")
    run_scenario("misclassify_nominal_uart_case", "REJECT", data, "in-envelope cases violate")

    data = copy.deepcopy(base)
    mutate_case(data, lambda c: c.get("bit_period_cycles") == 436, "rtl_model_match", False)
    run_scenario("inject_rtl_reference_mismatch", "REJECT", data, "in-envelope cases violate")

    data = copy.deepcopy(base)
    data["replay"]["silent_misdecode_reproduced"] = False
    run_scenario("erase_counterexample_reproduction", "REJECT", data, "was not reproduced")

    data = copy.deepcopy(base)
    data["timing_audit"]["in_envelope_passed"] = 383
    run_scenario("corrupt_in_envelope_pass_count", "REJECT", data, "pass count disagrees")

    data = copy.deepcopy(base)
    data["matrix"]["source_hashes"]["production_rtl_sha256"] = "0" * 64
    run_scenario("stale_production_rtl_hash", "REJECT", data, "hash is stale")

    data = copy.deepcopy(base)
    data["evidence_audit"]["status"] = "FAIL"
    run_scenario("mark_evidence_audit_failed", "REJECT", data, "status is not PASS")

    all_passed = all(item["test_passed"] for item in scenarios)
    report = {
        "tool": "TRACEFORGE",
        "version": "UART negative controls v0.1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all_passed else "FAIL",
        "scenarios_passed": sum(item["test_passed"] for item in scenarios),
        "scenarios_total": len(scenarios),
        "scenarios_failed": sum(not item["test_passed"] for item in scenarios),
        "production_rtl_sha256": actual_rtl_hash,
        "rtl_unchanged_by_test": True,
        "source_evidence_files_modified": False,
        "scenarios": scenarios,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# TRACEFORGE â€” UART Negative Controls v0.1",
        "",
        f"- Status: **{report['status']}**",
        f"- Scenarios passed: {report['scenarios_passed']}/{report['scenarios_total']}",
        f"- Production RTL SHA-256: `{actual_rtl_hash}`",
        "- Existing source evidence files modified: **No**",
        "- Production RTL modified: **No**",
        "",
        "## Results",
        "",
        "| Scenario | Expected | Observed | Test | Detection |",
        "|---|---|---|---|---|",
    ]
    for item in scenarios:
        detection = "; ".join(item["detected"]) or "none"
        lines.append(f"| {item['scenario']} | {item['expected']} | {item['observed']} | {'PASS' if item['test_passed'] else 'FAIL'} | {detection} |")
    lines.extend([
        "",
        "These are checker-level negative controls over temporary in-memory evidence mutations. They do not alter the source reports and do not constitute a fix for the known UART receiver limitation.",
        "",
    ])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "status": report["status"],
        "scenarios_passed": report["scenarios_passed"],
        "scenarios_total": report["scenarios_total"],
        "scenarios_failed": report["scenarios_failed"],
        "json_report": str(OUT_JSON),
        "markdown_report": str(OUT_MD),
    }, indent=2))
    for item in scenarios:
        print(f"{'PASS' if item['test_passed'] else 'FAIL'}: {item['scenario']} -> {item['observed']}")
        for message in item["detected"]:
            print(f"  detected: {message}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"UART negative controls could not complete: {exc}", file=sys.stderr)
        raise
