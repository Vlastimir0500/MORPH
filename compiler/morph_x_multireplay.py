"""MORPH X M4: exact-cycle, fail-closed multi-pin capture-to-replay compiler.

Runs on the host against the *unchanged* MORPH V2 ISA. No atomic multi-pin
output instruction is claimed. Captures with simultaneous selected-pin edges,
impossible inter-DRIVE timing, or inconsistent masks are rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from morph_assembler_v2 import AssemblyError, assemble, disassemble
from morph_x_replay import ReplayError, wait_instructions
from morph_x_trace import CLOCK_HZ, decode_capture

SCHEMA = "morph-x.multi-pin-ir.v1"
MAX_WORDS = 64


def _integer(x: Any, field: str, low: int, high: int) -> int:
    if type(x) is not int or not low <= x <= high:
        raise ReplayError(f"{field} must be an integer in {low}..{high}")
    return x


def _pins(pins: Any) -> list[int]:
    if not isinstance(pins, list) or not 1 <= len(pins) <= 8:
        raise ReplayError("pins must be a nonempty list of at most eight pins")
    for i, pin in enumerate(pins):
        _integer(pin, f"pins[{i}]", 0, 7)
    if pins != sorted(set(pins)):
        raise ReplayError("pins must be unique and sorted in ascending order")
    return pins


def validate_multi_ir(ir: Any) -> None:
    """Validate schedule semantics before compiling any output-driving code."""
    if not isinstance(ir, dict) or set(ir) != {"schema", "clock_hz", "pins", "events"}:
        raise ReplayError("multi-pin IR requires exactly schema, clock_hz, pins, events")
    if ir["schema"] != SCHEMA:
        raise ReplayError(f"unsupported multi-pin IR schema: {ir['schema']!r}")
    if _integer(ir["clock_hz"], "clock_hz", 1, 1_000_000_000) != CLOCK_HZ:
        raise ReplayError(f"V2 replay requires clock_hz={CLOCK_HZ}")
    pins = _pins(ir["pins"])
    events = ir["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= 61:
        raise ReplayError("events must be a nonempty list of at most 61 transitions")
    used = set()
    values: dict[int, int] = {}
    previous_cycle: int | None = None
    for i, event in enumerate(events):
        if not isinstance(event, dict) or set(event) != {"cycle", "pin", "value"}:
            raise ReplayError(f"events[{i}] must contain exactly cycle, pin, value")
        cycle = _integer(event["cycle"], f"events[{i}].cycle", 0, 524_280)
        pin = _integer(event["pin"], f"events[{i}].pin", 0, 7)
        value = _integer(event["value"], f"events[{i}].value", 0, 1)
        if pin not in pins:
            raise ReplayError(f"events[{i}].pin {pin} is not declared in pins")
        if i == 0 and cycle != 0:
            raise ReplayError("first selected event must occur at relative cycle 0")
        if previous_cycle is not None:
            if cycle <= previous_cycle:
                raise ReplayError("simultaneous or non-increasing selected-pin events are unsupported by V2")
            # V2 FETCH/EXEC is single issue; WAIT instructions add 2..257 cycles.
            # The scheduler cannot reproduce gaps of 1 or 3 clock cycles.
            wait_instructions(cycle - previous_cycle)
        if pin in values and values[pin] == value:
            raise ReplayError(f"pin {pin} repeats the same driven level: not a transition")
        values[pin] = value
        used.add(pin)
        previous_cycle = cycle
    if used != set(pins):
        raise ReplayError("each declared pin must have at least one transition")


def capture_to_multi_ir(frame: dict, pins: list[int]) -> dict:
    """Build deterministic cross-pin schedule from true capture timestamps.

    Never derives transitions for unselected pins; requires complete capture
    without overflow. First record's changed mask cannot be independently
    checked because pre-trigger pin levels are not recorded.
    """
    selected_pins = _pins(pins)
    try:
        decoded = decode_capture(frame)
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise ReplayError(f"invalid capture: {exc}") from exc
    if decoded["overflow"]:
        raise ReplayError("capture overflow: missing transitions cannot be replayed")

    mask = sum(1 << pin for pin in selected_pins)
    events: list[dict[str, int]] = []
    previous_levels: int | None = None
    absolute = 0
    for index, entry in enumerate(decoded["events"]):
        level = entry["levels"]
        changed = entry["changed"]
        if previous_levels is not None and (previous_levels ^ level) != changed:
            raise ReplayError(f"capture event {index}: changed mask inconsistent with previous levels")
        previous_levels = level
        if index:
            absolute += entry["delta_cycles"]
        chosen = changed & mask
        if chosen.bit_count() > 1:
            raise ReplayError("simultaneous selected-pin transitions require an atomic hardware instruction")
        if chosen:
            pin = chosen.bit_length() - 1
            events.append({"cycle": absolute, "pin": pin,
                           "value": (level >> pin) & 1})
    if not events:
        raise ReplayError("capture has no transitions on the selected pins")
    origin = events[0]["cycle"]
    ir = {"schema": SCHEMA, "clock_hz": CLOCK_HZ,
          "pins": selected_pins,
          "events": [{**event, "cycle": event["cycle"] - origin} for event in events]}
    validate_multi_ir(ir)
    return ir


def compile_multi_ir(ir: dict) -> tuple[str, list[int]]:
    validate_multi_ir(ir)
    commands: list[str] = []
    previous_cycle: int | None = None
    for event in ir["events"]:
        if previous_cycle is not None:
            commands.extend(wait_instructions(event["cycle"] - previous_cycle))
        commands.append(f"DRIVE {event['pin']}, {event['value']}")
        previous_cycle = event["cycle"]
    # Drives are held independently until all selected output pins are released.
    for pin in ir["pins"]:
        commands.append(f"RELEASE {pin}")
    commands.append("HALT")
    if len(commands) > MAX_WORDS:
        raise ReplayError(f"replay requires {len(commands)} words, V2 capacity is {MAX_WORDS}")
    source = "\n".join(commands) + "\n"
    try:
        words = assemble(source)
        if disassemble(words) != commands:
            raise ReplayError("assembler/disassembler round-trip mismatch")
    except (AssemblyError, ValueError) as exc:
        raise ReplayError(f"assembler rejected multi-pin replay: {exc}") from exc
    return source, words


def verify_multi_model(ir: dict, words: list[int]) -> dict:
    """Compare every scheduled DRIVE against the production V2 reference model."""
    validate_multi_ir(ir)
    sim_dir = Path(__file__).resolve().parents[1] / "sim"
    if str(sim_dir) not in sys.path:
        sys.path.insert(0, str(sim_dir))
    from morph_isa_model_v2 import MorphISAModelV2

    expected = ir["events"]
    selected_mask = sum(1 << pin for pin in ir["pins"])
    model = MorphISAModelV2()
    model.load_program(words)
    model.step(rst_n=False, pin_in=0)
    observed: list[dict[str, int]] = []
    release_seen: set[int] = set()
    # WAIT n has n extra WAIT cycles, bounded at compile time.
    limit = 10 + 4 * len(words) + sum(
        word & 0xFF for word in words if (word >> 12) == 3
    )
    halt_cycle = None
    for _ in range(limit):
        snap = model.step(rst_n=True, pin_in=0)
        if snap.fault:
            raise ReplayError("production model fault during multi-pin replay")
        if snap.pin_oe & ~selected_mask:
            raise ReplayError("production model unexpectedly enabled an undeclared pin")
        if snap.executed == "DRIVE":
            idx = len(observed)
            if idx >= len(expected):
                raise ReplayError("too many DRIVE instructions executed")
            requested = expected[idx]
            pin = requested["pin"]
            actual_pin = (snap.instruction >> 8) & 0xF
            if actual_pin != pin:
                raise ReplayError(f"DRIVE pin mismatch: expected {pin}, RTL model encoded {actual_pin}")
            if not (snap.pin_oe & (1 << pin)):
                raise ReplayError(f"DRIVE failed to enable pin {pin}")
            level = int(bool(snap.pin_out & (1 << pin)))
            observed.append({"cycle": snap.cycle, "pin": pin, "value": level})
        elif snap.executed == "RELEASE":
            # Order of RELEASE matches sorted declared pins, after all drives.
            next_index = len(release_seen)
            if next_index >= len(ir["pins"]):
                raise ReplayError("unexpected additional RELEASE")
            pin = ir["pins"][next_index]
            actual_pin = (snap.instruction >> 8) & 0xF
            if actual_pin != pin:
                raise ReplayError(f"RELEASE pin mismatch: expected {pin}, got {actual_pin}")
            if snap.pin_oe & (1 << pin):
                raise ReplayError(f"pin {pin} remained enabled after RELEASE")
            release_seen.add(pin)
        elif snap.executed == "HALT":
            halt_cycle = snap.cycle
            break
    if halt_cycle is None:
        raise ReplayError("multi-pin replay did not reach HALT")
    if model.pin_oe != 0 or release_seen != set(ir["pins"]):
        raise ReplayError("multi-pin replay did not release all selected pins")
    if len(observed) != len(expected):
        raise ReplayError("multi-pin replay DRIVE count mismatch")
    first = observed[0]["cycle"]
    relative = [{**entry, "cycle": entry["cycle"] - first} for entry in observed]
    if relative != expected:
        raise ReplayError(f"multi-pin timing/value mismatch: expected {expected}, got {relative}")
    return {"model_verified": True, "observed": relative,
            "first_drive_model_cycle": first,
            "halt_model_cycle": halt_cycle, "all_pins_released": True}


def compile_and_verify_multi(ir: dict) -> dict:
    source, words = compile_multi_ir(ir)
    verification = verify_multi_model(ir, words)
    encoded = "".join(f"{word:04X}\n" for word in words)
    canonical = json.dumps(ir, sort_keys=True, separators=(",", ":"))
    report = {
        "schema": "morph-x.multi-replay-report.v1",
        "ir_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "program_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "instruction_count": len(words), "clock_hz": CLOCK_HZ,
        "pins": ir["pins"], "expected_relative_cycles": ir["events"],
        "verification": verification,
        "limitations": [
            "single-issue V2 cannot reproduce simultaneous pin transitions",
            "exact inter-DRIVE gaps of 1 or 3 cycles are unsupported",
            "capture records only eight events and drops transitions while readback is active",
            "output-enable activation/release are not input edge equivalents",
            "16-bit timestamps can conceal full counter wraps",
            "only digital push-pull levels are modeled; no analog or wire-level timing certification",
            "host-side compilation; no automatic on-chip protocol inference",
        ],
    }
    return {"ir": ir, "assembly": source, "hex": encoded, "report": report}


def main() -> None:
    p = argparse.ArgumentParser(description="MORPH X exact multi-pin replay compiler (V2 profile)")
    p.add_argument("source", type=Path, help="raw capture JSON or multi-pin IR JSON")
    p.add_argument("--pins", nargs="+", type=int, help="selected ascending pins when source is raw capture")
    p.add_argument("--output-dir", type=Path, default=Path("build/morph-x-multireplay"))
    a = p.parse_args()
    try:
        source = json.loads(a.source.read_text(encoding="utf-8"))
        if isinstance(source, dict) and "schema" in source:
            if a.pins is not None and a.pins != source.get("pins"):
                raise ReplayError("--pins does not match IR pins")
            ir = source
        else:
            if a.pins is None:
                raise ReplayError("--pins is required for raw capture")
            ir = capture_to_multi_ir(source, a.pins)
        result = compile_and_verify_multi(ir)
        a.output_dir.mkdir(parents=True, exist_ok=True)
        outputs = {
            "multi.ir.json": json.dumps(result["ir"], indent=2) + "\n",
            "multi.morph": result["assembly"],
            "multi.hex": result["hex"],
            "multi.report.json": json.dumps(result["report"], indent=2) + "\n",
        }
        for name, contents in outputs.items():
            (a.output_dir / name).write_text(contents, encoding="utf-8")
        print(f"MULTI-PIN V2 MODEL VERIFIED: {len(ir['events'])} events / "
              f"{result['report']['instruction_count']} words / pins={ir['pins']}")
        print(f"Artifacts: {a.output_dir}")
    except (OSError, TypeError, KeyError, ValueError, json.JSONDecodeError) as exc:
        p.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
