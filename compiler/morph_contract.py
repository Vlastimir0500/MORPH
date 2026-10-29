import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
sys.path.insert(0, str(ROOT / "sim"))

from morph_assembler import AssemblyError, OPCODES, PROGRAM_DEPTH, assemble, disassemble
from morph_isa_model import MorphISAModel


class ContractError(ValueError):
    pass


def _integer(value, field, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ContractError(f"{field} must be an integer from {low} to {high}")


def _validate_event_list(events, field, max_cycle, max_value):
    if not isinstance(events, list):
        raise ContractError(f"{field} must be a list")
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ContractError(f"{field}[{index}] must be an object")
        if set(event) != {"cycle", "value"}:
            raise ContractError(f"{field}[{index}] must contain exactly cycle and value")
        _integer(event["cycle"], f"{field}[{index}].cycle", 1, max_cycle)
        _integer(event["value"], f"{field}[{index}].value", 0, max_value)


def validate_contract(contract):
    if not isinstance(contract, dict):
        raise ContractError("contract must be a JSON object")
    for key in ("schema_version", "name", "source", "limits", "requirements"):
        if key not in contract:
            raise ContractError(f"missing contract field: {key}")
    if contract["schema_version"] != 1:
        raise ContractError("schema_version must be 1")
    for key in ("name", "source"):
        if not isinstance(contract[key], str) or not contract[key].strip():
            raise ContractError(f"{key} must be a non-empty string")

    limits = contract["limits"]
    requirements = contract["requirements"]
    if not isinstance(limits, dict) or not isinstance(requirements, dict):
        raise ContractError("limits and requirements must be JSON objects")
    _integer(limits.get("max_program_words"), "max_program_words", 1, PROGRAM_DEPTH)
    _integer(limits.get("max_wait_cycles"), "max_wait_cycles", 0, 255)

    mnemonics = requirements.get("required_mnemonics", [])
    if not isinstance(mnemonics, list) or any(not isinstance(m, str) for m in mnemonics):
        raise ContractError("required_mnemonics must be a list of strings")
    unknown = sorted(set(mnemonics) - set(OPCODES))
    if unknown:
        raise ContractError("unknown required mnemonics: " + ", ".join(unknown))

    drives = requirements.get("drive_sequence", [])
    if not isinstance(drives, list) or any(
        isinstance(v, bool) or not isinstance(v, int) or v not in (0, 1) for v in drives
    ):
        raise ContractError("drive_sequence may contain only integer values 0 and 1")
    must_branch = requirements.get("must_have_backward_branch", False)
    if not isinstance(must_branch, bool):
        raise ContractError("must_have_backward_branch must be a boolean")

    scenarios = contract.get("temporal_scenarios", [])
    if not isinstance(scenarios, list):
        raise ContractError("temporal_scenarios must be a list")
    if len(scenarios) > 64:
        raise ContractError("temporal_scenarios cannot contain more than 64 scenarios")
    names = set()
    for index, scenario in enumerate(scenarios):
        prefix = f"temporal_scenarios[{index}]"
        if not isinstance(scenario, dict):
            raise ContractError(f"{prefix} must be an object")
        name = scenario.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ContractError(f"{prefix}.name must be a non-empty string")
        if name in names:
            raise ContractError(f"duplicate temporal scenario name: {name}")
        names.add(name)
        trace = scenario.get("pin_trace")
        if not isinstance(trace, list) or not 1 <= len(trace) <= 4096:
            raise ContractError(f"{prefix}.pin_trace must contain 1 to 4096 samples")
        if any(isinstance(v, bool) or not isinstance(v, int) or v not in (0, 1) for v in trace):
            raise ContractError(f"{prefix}.pin_trace must contain only integer values 0 and 1")
        expected = scenario.get("expect")
        if not isinstance(expected, dict) or not expected:
            raise ContractError(f"{prefix}.expect must be a non-empty object")
        allowed = {"pin_out_transitions", "shift_reg_transitions"}
        unknown_expectations = set(expected) - allowed
        if unknown_expectations:
            raise ContractError(f"{prefix}.expect contains unsupported signals: {sorted(unknown_expectations)}")
        max_cycle = len(trace) + 1
        for key, max_value in (("pin_out_transitions", 1), ("shift_reg_transitions", 255)):
            if key in expected:
                _validate_event_list(expected[key], f"{prefix}.expect.{key}", max_cycle, max_value)


def _temporal_result(source, scenario):
    words = assemble(source)
    model = MorphISAModel()
    model.load_program(words)
    reset_snapshot = model.step(rst_n=False, pin_in=0)
    previous_pin_out = reset_snapshot.pin_out
    previous_shift_reg = reset_snapshot.shift_reg
    observed = {"pin_out_transitions": [], "shift_reg_transitions": []}

    for pin in scenario["pin_trace"]:
        snapshot = model.step(pin_in=pin)
        if snapshot.pin_out != previous_pin_out:
            observed["pin_out_transitions"].append(
                {"cycle": snapshot.cycle, "value": snapshot.pin_out}
            )
        if snapshot.shift_reg != previous_shift_reg:
            observed["shift_reg_transitions"].append(
                {"cycle": snapshot.cycle, "value": snapshot.shift_reg}
            )
        previous_pin_out = snapshot.pin_out
        previous_shift_reg = snapshot.shift_reg

    signal_checks = []
    for signal, expected_events in scenario["expect"].items():
        actual_events = observed[signal]
        signal_checks.append({
            "signal": signal,
            "passed": actual_events == expected_events,
            "expected": expected_events,
            "observed": actual_events,
        })
    return {
        "name": scenario["name"],
        "status": "PASS" if all(item["passed"] for item in signal_checks) else "FAIL",
        "cycle_convention": "cycle 1 is reset; pin_trace[0] is sampled at cycle 2",
        "signal_checks": signal_checks,
        "observed_transitions": observed,
    }


def verify_program(source, contract, source_name="<memory>"):
    validate_contract(contract)
    try:
        words = assemble(source)
        instructions = disassemble(words)
    except AssemblyError as exc:
        raise ContractError(f"assembly failed: {exc}") from exc

    limits = contract["limits"]
    requirements = contract["requirements"]
    present = {line.split()[0] for line in instructions}
    missing = sorted(set(requirements.get("required_mnemonics", [])) - present)
    drives = [int(line.split()[1]) for line in instructions if line.startswith("DRIVE ")]
    waits = [int(line.split()[1]) for line in instructions if line.startswith("WAIT ")]
    backward = []
    for address, line in enumerate(instructions):
        if line.startswith("BRANCH "):
            target = int(line.split()[1])
            if target < address:
                backward.append({"address": address, "target": target})

    checks = [
        {"id": "program_depth", "passed": len(words) <= limits["max_program_words"],
         "actual": len(words), "limit": limits["max_program_words"]},
        {"id": "required_mnemonics", "passed": not missing, "missing": missing,
         "required": requirements.get("required_mnemonics", [])},
        {"id": "drive_sequence", "passed": drives == requirements.get("drive_sequence", []),
         "actual": drives, "expected": requirements.get("drive_sequence", [])},
        {"id": "wait_bound", "passed": max(waits, default=0) <= limits["max_wait_cycles"],
         "actual_max_wait": max(waits, default=0), "limit": limits["max_wait_cycles"]},
    ]
    if requirements.get("must_have_backward_branch", False):
        checks.append({"id": "backward_branch", "passed": bool(backward),
                       "actual": backward, "required": True})

    temporal_scenarios = [_temporal_result(source, scenario)
                          for scenario in contract.get("temporal_scenarios", [])]
    if temporal_scenarios:
        checks.append({
            "id": "temporal_scenarios",
            "passed": all(scenario["status"] == "PASS" for scenario in temporal_scenarios),
            "passed_count": sum(scenario["status"] == "PASS" for scenario in temporal_scenarios),
            "total_count": len(temporal_scenarios),
        })

    return {
        "schema_version": 1,
        "contract": contract["name"],
        "source": source_name,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "status": "PASS" if all(check["passed"] for check in checks) else "FAIL",
        "program_words": len(words),
        "words_hex": [f"{word:04X}" for word in words],
        "disassembly": [
            {"address": i, "word": f"{words[i]:04X}", "instruction": line}
            for i, line in enumerate(instructions)
        ],
        "max_wait_cycles": max(waits, default=0),
        "backward_branches": backward,
        "checks": checks,
        "temporal_scenarios": temporal_scenarios,
    }


def run_contract(path, output=None):
    path = Path(path).resolve()
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read contract {path}: {exc}") from exc
    validate_contract(contract)
    source_path = (path.parent / contract["source"]).resolve()
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"cannot read source {source_path}: {exc}") from exc

    report = verify_program(source, contract, str(source_path))
    destination = Path(output) if output else ROOT / "reports" / f"{contract['name']}.contract-report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report, destination


def main():
    parser = argparse.ArgumentParser(description="Statically and temporally verify a MORPH protocol contract")
    parser.add_argument("contract", help="path to a JSON protocol contract")
    parser.add_argument("-o", "--output", help="optional report path")
    args = parser.parse_args()
    try:
        report, path = run_contract(args.contract, args.output)
    except ContractError as exc:
        print(f"CONTRACT ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Contract: {report['contract']}")
    print(f"Status: {report['status']}")
    print(f"Program words: {report['program_words']}")
    print(f"Maximum WAIT: {report['max_wait_cycles']} cycles")
    print(f"Report: {path}")
    for check in report["checks"]:
        print(f"{'PASS' if check['passed'] else 'FAIL'}: {check['id']}")
    for scenario in report["temporal_scenarios"]:
        print(f"{scenario['status']}: temporal scenario {scenario['name']}")
        for signal_check in scenario["signal_checks"]:
            print(f"  {'PASS' if signal_check['passed'] else 'FAIL'}: {signal_check['signal']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
