"""MORPH X Temporal IR v1: conservative single-pin capture-to-firmware replay.

No device/hardware interface is claimed. The first observed transition is
retimed to the first DRIVE, and only the relative gaps are guaranteed by the
V2 reference-model checker. Unsupported schedules fail closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from morph_assembler_v2 import AssemblyError, assemble, disassemble
from morph_x_trace import CLOCK_HZ, decode_capture

SCHEMA = "morph-x.temporal-ir.v1"
MAX_EVENTS = 8
MAX_PROGRAM_WORDS = 64


class ReplayError(ValueError):
    pass


def require_int(value: Any, name: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ReplayError(f"{name} must be an integer in {lower}..{upper}")
    return value


def capture_to_ir(frame: dict, pin: int) -> dict:
    """Translate captured synchronized input transitions to one-pin Temporal IR."""
    require_int(pin, "pin", 0, 7)
    decoded = decode_capture(frame)
    if decoded["overflow"]:
        raise ReplayError("capture overflow: events lost, replay is unsafe")
    events = decoded["events"]
    previous_levels = None
    for event in events:
        if previous_levels is not None:
            if (previous_levels ^ event["levels"]) != event["changed"]:
                raise ReplayError("inconsistent changed mask or missing captured event")
        previous_levels = event["levels"]

    chosen = []
    accumulated = 0
    for index, event in enumerate(events):
        if index:
            accumulated += event["delta_cycles"]
        if event["changed"] & (1 << pin):
            chosen.append((accumulated, (event["levels"] >> pin) & 1))
    if not chosen:
        raise ReplayError(f"no captured transitions on pin {pin}")
    origin = chosen[0][0]
    ir = {
        "schema": SCHEMA,
        "clock_hz": CLOCK_HZ,
        "pin": pin,
        "events": [{"cycle": cycle - origin, "value": value} for cycle, value in chosen],
    }
    validate_ir(ir)
    return ir


def validate_ir(ir: dict) -> None:
    if not isinstance(ir, dict) or set(ir) != {"schema", "clock_hz", "pin", "events"}:
        raise ReplayError("Temporal IR must have exactly schema, clock_hz, pin and events")
    if ir["schema"] != SCHEMA:
        raise ReplayError(f"unsupported schema: {ir['schema']!r}")
    require_int(ir["clock_hz"], "clock_hz", 1, 1_000_000_000)
    if ir["clock_hz"] != CLOCK_HZ:
        raise ReplayError(f"clock mismatch: this V2 profile requires {CLOCK_HZ} Hz")
    require_int(ir["pin"], "pin", 0, 7)
    events = ir["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise ReplayError("events must contain 1..8 transitions")
    previous_cycle = None
    previous_value = None
    for index, event in enumerate(events):
        if not isinstance(event, dict) or set(event) != {"cycle", "value"}:
            raise ReplayError(f"events[{index}] must contain exactly cycle and value")
        cycle = require_int(event["cycle"], f"events[{index}].cycle", 0, 524_280)
        value = require_int(event["value"], f"events[{index}].value", 0, 1)
        if index == 0 and cycle != 0:
            raise ReplayError("first event must be retimed to cycle zero")
        if previous_cycle is not None and cycle <= previous_cycle:
            raise ReplayError("event cycles must increase strictly")
        if previous_value is not None and value == previous_value:
            raise ReplayError("two consecutive events cannot have identical levels")
        previous_cycle, previous_value = cycle, value


def wait_instructions(gap: int) -> list[str]:
    """Exact fetch/execute timing: DRIVE-to-DRIVE costs 2 cycles;
    a WAIT n adds 2 cycles if n=0, otherwise 2+n cycles.
    """
    require_int(gap, "transition gap", 1, 524_280)
    if gap == 2:
        return []
    if gap in (1, 3):
        raise ReplayError(f"unrepresentable {gap}-cycle gap on single-issue V2")
    remain = gap - 2
    commands = []
    while remain:
        if remain == 1:
            raise ReplayError("internal scheduler error: single-cycle WAIT overhead")
        chunk = min(257, remain)
        if remain - chunk == 1:
            chunk -= 1
        assert 2 <= chunk <= 257
        commands.append("WAIT 0" if chunk == 2 else f"WAIT {chunk - 2}")
        remain -= chunk
    return commands


def compile_ir(ir: dict) -> tuple[str, list[int]]:
    validate_ir(ir)
    pin = ir["pin"]
    commands: list[str] = []
    previous_cycle = None
    for event in ir["events"]:
        if previous_cycle is not None:
            commands.extend(wait_instructions(event["cycle"] - previous_cycle))
        commands.append(f"DRIVE {pin}, {event['value']}")
        previous_cycle = event["cycle"]
    commands.extend([f"RELEASE {pin}", "HALT"])
    if len(commands) > MAX_PROGRAM_WORDS:
        raise ReplayError(f"replay requires {len(commands)} words, V2 has only 64")
    source = "\n".join(commands) + "\n"
    try:
        words = assemble(source)
        if disassemble(words) != commands:
            raise ReplayError("assembler/disassembler round-trip mismatch")
    except (AssemblyError, ValueError) as exc:
        raise ReplayError(f"assembler rejected replay: {exc}") from exc
    return source, words


def verify_with_model(ir: dict, words: list[int]) -> dict:
    """Independent behavioral check of schedule against the V2 cycle model."""
    validate_ir(ir)
    # The model is provided by the existing repository at run time, not by this kit.
    sim_dir = Path(__file__).resolve().parents[1] / "sim"
    if str(sim_dir) not in sys.path:
        sys.path.insert(0, str(sim_dir))
    from morph_isa_model_v2 import MorphISAModelV2

    pin = ir["pin"]
    bit = 1 << pin
    engine = MorphISAModelV2()
    engine.load_program(words)
    engine.step(rst_n=False)
    observed = []
    halted = False
    released = False
    # Bound simulation using total programmed waits plus worst-case per instruction.
    limit = 10 + 4 * len(words) + sum(
        (word & 0xFF) for word in words if ((word >> 12) & 0xF) == 3
    )
    for _ in range(limit):
        snapshot = engine.step(rst_n=True)
        if snapshot.fault:
            raise ReplayError("V2 model entered a fault state during replay")
        if snapshot.executed == "DRIVE":
            if not (snapshot.pin_oe & bit):
                raise ReplayError("V2 model drove without enabling the output")
            observed.append({"cycle": snapshot.cycle,
                             "value": int(bool(snapshot.pin_out & bit))})
        if snapshot.executed == "RELEASE":
            released = not bool(snapshot.pin_oe & bit)
        if snapshot.executed == "HALT":
            halted = True
            break
    if not halted or not released:
        raise ReplayError("V2 model failed to halt after releasing selected pin")
    if len(observed) != len(ir["events"]):
        raise ReplayError(f"V2 model issued {len(observed)} DRIVE events, expected {len(ir['events'])}")
    first = observed[0]["cycle"]
    relative = [{"cycle": row["cycle"] - first, "value": row["value"]}
                for row in observed]
    if relative != ir["events"]:
        raise ReplayError(f"model timing mismatch: expected {ir['events']!r}, observed {relative!r}")
    return {"model_verified": True,
            "observed": relative,
            "first_drive_model_cycle": first,
            "released_before_halt": True,
            "halt_model_cycle": snapshot.cycle}


def compile_and_verify(ir: dict) -> dict:
    assembly, words = compile_ir(ir)
    evidence = verify_with_model(ir, words)
    program_hex = "".join(f"{w:04X}\n" for w in words)
    ir_json = json.dumps(ir, sort_keys=True, separators=(",", ":"))
    return {"ir": ir, "assembly": assembly, "hex": program_hex,
            "report": {
                "schema": "morph-x.replay-report.v1",
                "ir_sha256": hashlib.sha256(ir_json.encode()).hexdigest(),
                "program_sha256": hashlib.sha256(program_hex.encode()).hexdigest(),
                "instruction_count": len(words),
                "selected_pin": ir["pin"],
                "clock_hz": ir["clock_hz"],
                "expected_relative_cycles": ir["events"],
                "verification": evidence,
                "limits": ["single push-pull output pin",
                           "at most eight source events",
                           "relative timing only; no phase alignment",
                           "no exact gaps of one or three cycles",
                           "no streaming or analog electrical behavior",
                           "16-bit capture timestamps can be ambiguous after a full wrap",
                           "model equivalence only; RTL differential verification pending"],
            }}


def main() -> None:
    parser = argparse.ArgumentParser(description="Conservative MORPH X capture-to-replay compiler")
    parser.add_argument("source", type=Path, help="raw capture JSON or Temporal IR v1 JSON")
    parser.add_argument("--pin", type=int, help="selected pin for raw capture (0..7)")
    parser.add_argument("--output-dir", type=Path, default=Path("build/morph-x-replay"))
    args = parser.parse_args()
    try:
        data = json.loads(args.source.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "schema" in data:
            if args.pin is not None and data.get("pin") != args.pin:
                raise ReplayError("--pin does not match the Temporal IR pin")
            ir = data
        else:
            if args.pin is None:
                raise ReplayError("--pin is required for raw capture input")
            ir = capture_to_ir(data, args.pin)
        result = compile_and_verify(ir)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, contents in [
            ("replay.ir.json", json.dumps(result["ir"], indent=2) + "\n"),
            ("replay.morph", result["assembly"]),
            ("replay.hex", result["hex"]),
            ("replay.report.json", json.dumps(result["report"], indent=2) + "\n"),
        ]:
            (args.output_dir / name).write_text(contents, encoding="utf-8")
        print(f"VERIFIED V2 MODEL TIMING: {len(result['ir']['events'])} events / "
              f"{result['report']['instruction_count']} words")
        print(f"Outputs: {args.output_dir}")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
