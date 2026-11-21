import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
sys.path.insert(0, str(ROOT / "sim"))

from morph_assembler_v2 import AssemblyError, OPCODES, assemble, disassemble
from morph_isa_model_v2 import MorphISAModelV2


class ContractError(ValueError):
    pass


SIGNAL_MAX = {
    "pin_out": 255,
    "pin_oe": 255,
    "sample_reg": 1,
    "shift_reg": 255,
    "fault": 1,
    "timed_out": 1,
}
FINAL_FIELDS = {"state", "pc", "pin_out", "pin_oe", "sample_reg", "shift_reg", "wait_count", "fault", "timed_out"}
VALID_STATES = {"FETCH", "EXEC", "WAIT", "EDGE_WAIT", "HALT"}


def _integer(value, field, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ContractError(f"{field} must be an integer from {low} to {high}")


def validate_contract(contract):
    if not isinstance(contract, dict):
        raise ContractError("contract must be a JSON object")
    required = {"schema_version", "name", "limits", "requirements", "program", "scenarios"}
    missing = sorted(required - set(contract))
    if missing:
        raise ContractError("missing contract fields: " + ", ".join(missing))
    unknown = sorted(set(contract) - (required | {"assumptions"}))
    if unknown:
        raise ContractError("unsupported contract fields: " + ", ".join(unknown))
    if contract["schema_version"] != 2:
        raise ContractError("schema_version must be 2 for the V2 ISA")
    if not isinstance(contract["name"], str) or not contract["name"].strip():
        raise ContractError("name must be a non-empty string")

    limits = contract["limits"]
    requirements = contract["requirements"]
    if not isinstance(limits, dict) or not isinstance(requirements, dict):
        raise ContractError("limits and requirements must be JSON objects")
    if set(limits) != {"max_program_words", "max_wait_cycles", "max_edge_timeout_cycles"}:
        raise ContractError("limits must define max_program_words, max_wait_cycles and max_edge_timeout_cycles")
    _integer(limits["max_program_words"], "max_program_words", 1, 64)
    _integer(limits["max_wait_cycles"], "max_wait_cycles", 0, 255)
    _integer(limits["max_edge_timeout_cycles"], "max_edge_timeout_cycles", 0, 127)

    if set(requirements) != {"required_mnemonics"}:
        raise ContractError("requirements must contain only required_mnemonics in schema v2")
    mnemonics = requirements["required_mnemonics"]
    if not isinstance(mnemonics, list) or any(not isinstance(item, str) for item in mnemonics):
        raise ContractError("required_mnemonics must be a list of strings")
    unknown_mnemonics = sorted(set(mnemonics) - set(OPCODES))
    if unknown_mnemonics:
        raise ContractError("unknown required mnemonics: " + ", ".join(unknown_mnemonics))

    program = contract["program"]
    if not isinstance(program, list) or not 1 <= len(program) <= 64:
        raise ContractError("program must contain 1 to 64 typed operations")
    for index, operation in enumerate(program):
        prefix = f"program[{index}]"
        if not isinstance(operation, dict) or not isinstance(operation.get("op"), str):
            raise ContractError(f"{prefix} must be an object with a string op")
        op = operation["op"]
        fields = {
            "drive": {"op", "pin", "value"},
            "wait_cycles": {"op", "cycles"},
            "wait_edge": {"op", "pin", "edge", "timeout_cycles"},
            "release": {"op", "pin"},
            "sample": {"op", "pin"},
            "shift": {"op"},
            "halt": {"op"},
        }.get(op)
        if fields is None:
            raise ContractError(f"{prefix}.op '{op}' is unsupported by the restricted V2 contract compiler")
        if set(operation) != fields:
            raise ContractError(f"{prefix} fields must be exactly: {', '.join(sorted(fields))}")
        if op in ("drive", "wait_edge", "release", "sample"):
            _integer(operation["pin"], f"{prefix}.pin", 0, 7)
        if op == "drive":
            _integer(operation["value"], f"{prefix}.value", 0, 1)
        elif op == "wait_cycles":
            _integer(operation["cycles"], f"{prefix}.cycles", 0, 255)
        elif op == "wait_edge":
            if operation["edge"] not in ("rising", "falling"):
                raise ContractError(f"{prefix}.edge must be 'rising' or 'falling'")
            _integer(operation["timeout_cycles"], f"{prefix}.timeout_cycles", 0, 127)
    if program[-1].get("op") != "halt":
        raise ContractError("program must end with halt in the restricted linear schema")
    if any(item.get("op") == "halt" for item in program[:-1]):
        raise ContractError("halt may appear only as the final program operation")

    assumptions = contract.get("assumptions", {})
    if not isinstance(assumptions, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in assumptions.items()):
        raise ContractError("assumptions must map strings to strings")

    scenarios = contract["scenarios"]
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 32:
        raise ContractError("scenarios must contain 1 to 32 scenarios")
    names = set()
    for index, scenario in enumerate(scenarios):
        prefix = f"scenarios[{index}]"
        if not isinstance(scenario, dict) or set(scenario) != {"name", "pin_trace", "expect"}:
            raise ContractError(f"{prefix} must contain exactly name, pin_trace and expect")
        name = scenario["name"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ContractError(f"{prefix}.name must be non-empty and unique")
        names.add(name)
        trace = scenario["pin_trace"]
        if not isinstance(trace, list) or not 1 <= len(trace) <= 4096:
            raise ContractError(f"{prefix}.pin_trace must contain 1 to 4096 8-bit samples")
        for sample_index, sample in enumerate(trace):
            _integer(sample, f"{prefix}.pin_trace[{sample_index}]", 0, 255)
        expected = scenario["expect"]
        if not isinstance(expected, dict) or set(expected) != {"transitions", "final"}:
            raise ContractError(f"{prefix}.expect must contain exactly transitions and final")
        transitions = expected["transitions"]
        final = expected["final"]
        if not isinstance(transitions, dict) or not transitions:
            raise ContractError(f"{prefix}.expect.transitions must be a non-empty object")
        unknown_signals = sorted(set(transitions) - set(SIGNAL_MAX))
        if unknown_signals:
            raise ContractError(f"{prefix} has unsupported transition signals: {', '.join(unknown_signals)}")
        max_cycle = len(trace) + 1
        for signal, events in transitions.items():
            if not isinstance(events, list):
                raise ContractError(f"{prefix}.expect.transitions.{signal} must be a list")
            for event_index, event in enumerate(events):
                event_prefix = f"{prefix}.expect.transitions.{signal}[{event_index}]"
                if not isinstance(event, dict) or set(event) != {"cycle", "value"}:
                    raise ContractError(f"{event_prefix} must contain exactly cycle and value")
                _integer(event["cycle"], f"{event_prefix}.cycle", 1, max_cycle)
                _integer(event["value"], f"{event_prefix}.value", 0, SIGNAL_MAX[signal])
        if not isinstance(final, dict) or not final or set(final) - FINAL_FIELDS:
            raise ContractError(f"{prefix}.expect.final must contain supported final signal values")
        for field, value in final.items():
            if field == "state":
                if not isinstance(value, str) or value not in VALID_STATES:
                    raise ContractError(f"{prefix}.expect.final.state is not a valid V2 state")
            elif field in ("fault", "timed_out"):
                if not isinstance(value, bool):
                    raise ContractError(f"{prefix}.expect.final.{field} must be a boolean")
            else:
                maximum = SIGNAL_MAX[field] if field in SIGNAL_MAX else 63 if field == "pc" else 255
                _integer(value, f"{prefix}.expect.final.{field}", 0, maximum)


def compile_contract(contract):
    validate_contract(contract)
    lines = []
    for operation in contract["program"]:
        op = operation["op"]
        if op == "drive":
            lines.append(f"DRIVE {operation['pin']}, {operation['value']}")
        elif op == "wait_cycles":
            lines.append(f"WAIT {operation['cycles']}")
        elif op == "wait_edge":
            edge = "RISE" if operation["edge"] == "rising" else "FALL"
            timeout = operation["timeout_cycles"]
            suffix = f", {timeout}" if timeout else ""
            lines.append(f"EDGE {operation['pin']}, {edge}{suffix}")
        elif op == "release":
            lines.append(f"RELEASE {operation['pin']}")
        elif op == "sample":
            lines.append(f"SAMPLE {operation['pin']}")
        elif op == "shift":
            lines.append("SHIFT")
        elif op == "halt":
            lines.append("HALT")
    return "\n".join(lines) + "\n"


def _collect_signals(snapshot):
    return {
        "pin_out": snapshot.pin_out,
        "pin_oe": snapshot.pin_oe,
        "sample_reg": snapshot.sample_reg,
        "shift_reg": snapshot.shift_reg,
        "fault": int(snapshot.fault),
        "timed_out": int(snapshot.timed_out),
    }


def _run_scenario(words, scenario):
    model = MorphISAModelV2()
    model.load_program(words)
    reset_snapshot = model.step(rst_n=False, pin_in=0)
    previous = _collect_signals(reset_snapshot)
    observed = {name: [] for name in SIGNAL_MAX}
    trace = []
    for pin_value in scenario["pin_trace"]:
        snapshot = model.step(pin_in=pin_value)
        values = _collect_signals(snapshot)
        for signal, value in values.items():
            if value != previous[signal]:
                observed[signal].append({"cycle": snapshot.cycle, "value": value})
        previous = values
        trace.append(snapshot)

    expected = scenario["expect"]
    transition_checks = []
    for signal, expected_events in expected["transitions"].items():
        actual_events = observed[signal]
        transition_checks.append({
            "signal": signal,
            "passed": actual_events == expected_events,
            "expected": expected_events,
            "observed": actual_events,
        })

    final_snapshot = trace[-1]
    final_actual = {
        "state": final_snapshot.state,
        "pc": final_snapshot.pc,
        "pin_out": final_snapshot.pin_out,
        "pin_oe": final_snapshot.pin_oe,
        "sample_reg": final_snapshot.sample_reg,
        "shift_reg": final_snapshot.shift_reg,
        "wait_count": final_snapshot.wait_count,
        "fault": final_snapshot.fault,
        "timed_out": final_snapshot.timed_out,
    }
    final_checks = []
    for field, expected_value in expected["final"].items():
        actual_value = final_actual[field]
        final_checks.append({
            "field": field,
            "passed": actual_value == expected_value,
            "expected": expected_value,
            "observed": actual_value,
        })

    checks = transition_checks + final_checks
    return {
        "name": scenario["name"],
        "status": "PASS" if all(item["passed"] for item in checks) else "FAIL",
        "pin_trace": scenario["pin_trace"],
        "cycle_convention": "cycle 1 is reset; pin_trace[0] is sampled at cycle 2",
        "transition_checks": transition_checks,
        "final_checks": final_checks,
        "observed_transitions": observed,
        "final_observed": final_actual,
    }


def verify_contract(contract, contract_name="<memory>"):
    validate_contract(contract)
    source = compile_contract(contract)
    try:
        words = assemble(source)
        instructions = disassemble(words)
    except AssemblyError as exc:
        raise ContractError(f"V2 assembly failed: {exc}") from exc

    limits = contract["limits"]
    required = contract["requirements"]["required_mnemonics"]
    present = {line.split()[0] for line in instructions}
    missing = sorted(set(required) - present)
    waits = [int(match.group(1)) for line in instructions if (match := re.fullmatch(r"WAIT (\d+)", line))]
    edge_timeouts = []
    unbounded_edge_waits = []
    for address, line in enumerate(instructions):
        match = re.fullmatch(r"EDGE ([0-7]), (?:RISE|FALL)(?:, (\d+))?", line)
        if match:
            timeout_text = match.group(2)
            if timeout_text is None or int(timeout_text) == 0:
                # An EDGE without a timeout is unbounded.
                unbounded_edge_waits.append(
                    {"address": address, "instruction": line}
                )
            else:
                edge_timeouts.append(int(timeout_text))

    static_checks = [
        {"id": "program_word_limit", "passed": len(words) <= limits["max_program_words"], "actual": len(words), "limit": limits["max_program_words"]},
        {"id": "required_mnemonics", "passed": not missing, "missing": missing, "required": required},
        {"id": "wait_cycle_limit", "passed": max(waits, default=0) <= limits["max_wait_cycles"], "actual_max_wait": max(waits, default=0), "limit": limits["max_wait_cycles"]},
        {
            "id": "edge_timeout_limit",
            "passed": (
                not unbounded_edge_waits
                and max(edge_timeouts, default=0)
                <= limits["max_edge_timeout_cycles"]
            ),
            "actual_max_edge_timeout": max(edge_timeouts, default=0),
            "unbounded_edge_waits": unbounded_edge_waits,
            "limit": limits["max_edge_timeout_cycles"],
        },
    ]
    scenarios = [_run_scenario(words, scenario) for scenario in contract["scenarios"]]
    return {
        "schema_version": 2,
        "contract": contract["name"],
        "contract_path": contract_name,
        "generated_source": source,
        "generated_source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "program_sha256": hashlib.sha256(b"".join(word.to_bytes(2, "big") for word in words)).hexdigest(),
        "status": "PASS" if all(check["passed"] for check in static_checks) and all(item["status"] == "PASS" for item in scenarios) else "FAIL",
        "assumptions": contract.get("assumptions", {}),
        "program_words": len(words),
        "words_hex": [f"{word:04X}" for word in words],
        "disassembly": [{"address": index, "word": f"{words[index]:04X}", "instruction": line} for index, line in enumerate(instructions)],
        "max_wait_cycles": max(waits, default=0),
        "max_edge_timeout_cycles": max(edge_timeouts, default=0),
        "static_checks": static_checks,
        "scenarios": scenarios,
    }


def run_contract(contract_path, output=None, assembly_output=None):
    contract_path = Path(contract_path).resolve()
    try:
        contract_bytes = contract_path.read_bytes()
        contract = json.loads(contract_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read contract {contract_path}: {exc}") from exc

    report = verify_contract(contract, str(contract_path))
    report["contract_sha256"] = hashlib.sha256(contract_bytes).hexdigest()
    if assembly_output:
        assembly_path = Path(assembly_output)
        assembly_path.parent.mkdir(parents=True, exist_ok=True)
        assembly_path.write_text(report["generated_source"], encoding="utf-8")
        report["generated_source_path"] = str(assembly_path)
    destination = Path(output) if output else ROOT / "reports" / f"{contract['name']}.v2-contract-report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report, destination


def main():
    parser = argparse.ArgumentParser(description="Compile and validate a restricted MORPH V2 temporal contract")
    parser.add_argument("contract", help="path to a V2 JSON protocol contract")
    parser.add_argument("-o", "--output", help="optional JSON report path")
    parser.add_argument("-a", "--assembly-output", help="optional generated MORPH assembly path")
    args = parser.parse_args()
    try:
        report, report_path = run_contract(args.contract, args.output, args.assembly_output)
    except ContractError as exc:
        print(f"CONTRACT ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Contract: {report['contract']}")
    print(f"Status: {report['status']}")
    print(f"Program words: {report['program_words']}")
    print(f"Generated source SHA-256: {report['generated_source_sha256']}")
    print(f"Program SHA-256: {report['program_sha256']}")
    for check in report["static_checks"]:
        print(f"{'PASS' if check['passed'] else 'FAIL'}: {check['id']}")
    for scenario in report["scenarios"]:
        print(f"{scenario['status']}: {scenario['name']}")
        for check in scenario["transition_checks"] + scenario["final_checks"]:
            print(f"  {'PASS' if check['passed'] else 'FAIL'}: {check.get('signal', check.get('field'))}")
    print(f"Report: {report_path}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
