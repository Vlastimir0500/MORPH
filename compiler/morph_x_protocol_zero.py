"""MORPH X M5: protocol-neutral digital challenge and independent event oracle.

The oracle never uses the production V2 model to create expected events. It
compares an observed top-level or hardware trace against a prior specification.
The built-in generator is explicitly a *self-test*, never a blind challenge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

SPEC_SCHEMA = "morph-x.protocol-zero.challenge.v1"
OBS_SCHEMA = "morph-x.protocol-zero.observation.v1"
JUDGE_SCHEMA = "morph-x.protocol-zero.judgment.v1"
CLOCK_HZ = 50_000_000
MAX_CAPTURE_EVENTS = 8
SOURCES = {"rtl-top", "gate-level", "physical", "offline-synthetic"}


class ChallengeError(ValueError):
    """Rejected challenge, captured input, or observed replay evidence."""


def _int(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ChallengeError(f"{name} must be an integer in {low}..{high}")
    return value


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def digest(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def validate_spec(spec: Any) -> None:
    """Validate *digital stimulus*, not whether the single-issue ISA supports it.

    Simultaneous events and 1/3-cycle gaps intentionally remain legal requests
    so the backend can demonstrate a fail-closed unsupported outcome.
    """
    if not isinstance(spec, dict) or set(spec) != {
        "schema", "challenge_id", "clock_hz", "pins", "initial_levels", "events"
    }:
        raise ChallengeError("challenge must contain exactly six specified fields")
    if spec["schema"] != SPEC_SCHEMA:
        raise ChallengeError("unsupported challenge schema")
    if not isinstance(spec["challenge_id"], str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", spec["challenge_id"]
    ):
        raise ChallengeError("challenge_id must be 1..80 safe ASCII characters")
    if _int(spec["clock_hz"], "clock_hz", 1, 1_000_000_000) != CLOCK_HZ:
        raise ChallengeError(f"this target requires {CLOCK_HZ} Hz")
    initial = _int(spec["initial_levels"], "initial_levels", 0, 255)
    pins = spec["pins"]
    if not isinstance(pins, list) or not 1 <= len(pins) <= 8:
        raise ChallengeError("pins must be a nonempty array of up to eight pins")
    for i, pin in enumerate(pins):
        _int(pin, f"pins[{i}]", 0, 7)
    if pins != sorted(set(pins)):
        raise ChallengeError("pins must be strictly sorted without duplicates")
    events = spec["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_CAPTURE_EVENTS:
        raise ChallengeError("challenge requires 1..8 digital transitions")
    current = {pin: (initial >> pin) & 1 for pin in pins}
    used = set()
    last_cycle = -1
    for i, event in enumerate(events):
        if not isinstance(event, dict) or set(event) != {"cycle", "pin", "value"}:
            raise ChallengeError(f"events[{i}] must contain exactly cycle, pin, value")
        cyc = _int(event["cycle"], f"events[{i}].cycle", 0, 524_280)
        pin = _int(event["pin"], f"events[{i}].pin", 0, 7)
        val = _int(event["value"], f"events[{i}].value", 0, 1)
        if pin not in pins:
            raise ChallengeError(f"events[{i}] references undeclared pin {pin}")
        if i == 0 and cyc != 0:
            raise ChallengeError("first event must be relative cycle zero")
        if cyc < last_cycle:
            raise ChallengeError("events must be ordered by nondecreasing cycle")
        if current[pin] == val:
            raise ChallengeError(f"events[{i}] does not change pin {pin}")
        current[pin] = val
        used.add(pin)
        last_cycle = cyc
    if used != set(pins):
        raise ChallengeError("each declared pin must be exercised")


def spec_to_ir(spec: dict) -> dict:
    validate_spec(spec)
    # Backend must independently verify exact schedulability: NEVER round gaps.
    from morph_x_multireplay import SCHEMA
    return {"schema": SCHEMA, "clock_hz": CLOCK_HZ,
            "pins": spec["pins"][:], "events": [dict(e) for e in spec["events"]]}


def generate_selftest_spec(seed: int) -> dict:
    """Deterministic synthetic challenges. NOT independent / NOT blind."""
    _int(seed, "seed", 0, 0xFFFFFFFF)
    rng = random.Random(seed)
    pins = [0, 1, 2, 3]
    first = pins[:]
    second = pins[:]
    rng.shuffle(first)
    rng.shuffle(second)
    events = []
    cyc = 0
    for i, pin in enumerate(first + second):
        if i:
            cyc += rng.choice([4, 5, 6, 8, 10, 12, 14])
        events.append({"cycle": cyc, "pin": pin, "value": 1 if i < 4 else 0})
    result = {"schema": SPEC_SCHEMA,
              "challenge_id": f"SELFTEST-{seed:08X}",
              "clock_hz": CLOCK_HZ, "pins": pins,
              "initial_levels": 0, "events": events}
    validate_spec(result)
    return result


def capture_fixture_from_spec(spec: dict, *, initial_stamp: int = 7) -> dict:
    """Generate test-only capture-register bytes; never hardware evidence."""
    validate_spec(spec)
    _int(initial_stamp, "initial_stamp", 0, 65535)
    # Hardware captures one changed-mask record per clock, including simultaneous
    # transitions (which the unchanged V2 replay backend will reject).
    levels = spec["initial_levels"]
    groups: list[tuple[int, list[dict]]] = []
    for event in spec["events"]:
        if groups and groups[-1][0] == event["cycle"]:
            groups[-1][1].append(event)
        else:
            groups.append((event["cycle"], [event]))
    rows = []
    for cycle, group in groups:
        changed = 0
        for entry in group:
            bit = 1 << entry["pin"]
            changed |= bit
            levels = (levels & ~bit) | (entry["value"] << entry["pin"])
        stamp = (initial_stamp + cycle) & 0xFFFF
        rows.append([levels, changed, stamp & 255, stamp >> 8])
    count = len(rows)
    status = 0x40 | count | (0x20 if count == 8 else 0)
    return {"status": status, "slots": rows}


def compare_capture_to_spec(frame: dict, spec: dict) -> dict:
    """Validate real capture bytes against prior challenge, including first edge."""
    validate_spec(spec)
    from morph_x_multireplay import capture_to_multi_ir
    from morph_x_trace import decode_capture

    decoded = decode_capture(frame)
    if decoded["overflow"]:
        raise ChallengeError("capture overflow makes challenge uninterpretable")
    if not decoded["events"]:
        raise ChallengeError("capture is empty")
    mask = sum(1 << pin for pin in spec["pins"])
    first = decoded["events"][0]
    if ((first["levels"] ^ spec["initial_levels"]) & mask) != (first["changed"] & mask):
        raise ChallengeError("first capture edge contradicts known initial pin levels")
    try:
        actual_ir = capture_to_multi_ir(frame, spec["pins"])
    except ValueError as exc:
        raise ChallengeError(f"invalid or unsupported captured trace: {exc}") from exc
    if actual_ir["events"] != spec["events"]:
        raise ChallengeError("capture edges do not match independently supplied challenge")
    return {"capture_verified": True, "event_count": len(actual_ir["events"]),
            "capture_sha256": digest(frame)}


def make_observation(spec: dict, transitions: list[dict], *, source: str,
                     released: bool, fault: bool = False,
                     unselected_output_enable_seen: bool = False) -> dict:
    validate_spec(spec)
    return {"schema": OBS_SCHEMA, "challenge_id": spec["challenge_id"],
            "source": source, "transitions": transitions,
            "released": released, "fault": fault,
            "unselected_output_enable_seen": unselected_output_enable_seen}


def judge_observation(spec: dict, observation: Any) -> dict:
    """Independent oracle: expected edge sequence comes only from the spec."""
    validate_spec(spec)
    if not isinstance(observation, dict) or set(observation) != {
        "schema", "challenge_id", "source", "transitions", "released",
        "fault", "unselected_output_enable_seen"
    }:
        raise ChallengeError("observation has missing or unexpected fields")
    if observation["schema"] != OBS_SCHEMA:
        raise ChallengeError("unsupported observation schema")
    if observation["challenge_id"] != spec["challenge_id"]:
        raise ChallengeError("challenge_id mismatch")
    if type(observation["source"]) is not str or observation["source"] not in SOURCES:
        raise ChallengeError("unknown evidence source; choose a declared observation source")
    for field in ("released", "fault", "unselected_output_enable_seen"):
        if type(observation[field]) is not bool:
            raise ChallengeError(f"observation.{field} must be a boolean")
    actual = observation["transitions"]
    if not isinstance(actual, list) or len(actual) > 512:
        raise ChallengeError("transitions must be a bounded array")
    for i, ev in enumerate(actual):
        if not isinstance(ev, dict) or set(ev) != {"cycle", "pin", "value"}:
            raise ChallengeError(f"transitions[{i}] has invalid fields")
        _int(ev["cycle"], f"transitions[{i}].cycle", 0, 1_000_000)
        _int(ev["pin"], f"transitions[{i}].pin", 0, 7)
        _int(ev["value"], f"transitions[{i}].value", 0, 1)
    expected = spec["events"]
    first_diff = next((i for i in range(min(len(actual), len(expected)))
                       if actual[i] != expected[i]), None)
    if first_diff is None and len(actual) != len(expected):
        first_diff = min(len(actual), len(expected))
    conditions = {
        "exact_transitions": first_diff is None,
        "released": observation["released"],
        "no_fault": not observation["fault"],
        "no_undeclared_drive": not observation["unselected_output_enable_seen"],
    }
    return {"schema": JUDGE_SCHEMA, "challenge_id": spec["challenge_id"],
            "accepted": all(conditions.values()), "conditions": conditions,
            "expected_count": len(expected), "observed_count": len(actual),
            "first_difference_index": first_diff,
            "source": observation["source"],
            "challenge_sha256": digest(spec),
            "observation_sha256": digest(observation),
            "blind_external_evaluation_claimed": False}


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MORPH X M5 Protocol Zero host tools; self-tests are not blind")
    sub = p.add_subparsers(dest="action", required=True)
    generate = sub.add_parser("generate-selftest", help="create an explicitly synthetic test challenge")
    generate.add_argument("--seed", type=int, required=True)
    generate.add_argument("--output", type=Path, required=True)
    prepare = sub.add_parser("prepare", help="compile an existing reviewer challenge for V2")
    prepare.add_argument("challenge", type=Path)
    prepare.add_argument("--capture", type=Path, help="optional actual raw capture JSON to compare")
    prepare.add_argument("--output-dir", type=Path, required=True)
    judge = sub.add_parser("judge", help="compare observed top-level waveform against prior challenge")
    judge.add_argument("challenge", type=Path)
    judge.add_argument("observation", type=Path)
    judge.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.action == "generate-selftest":
            spec = generate_selftest_spec(args.seed)
            _write_json(args.output, spec)
            print(f"SYNTHETIC SELF-TEST ONLY: {spec['challenge_id']}")
            return 0
        spec = json.loads(args.challenge.read_text(encoding="utf-8"))
        validate_spec(spec)
        if args.action == "judge":
            obs = json.loads(args.observation.read_text(encoding="utf-8"))
            verdict = judge_observation(spec, obs)
            _write_json(args.output, verdict)
            print("OBSERVED TRACE ACCEPTED" if verdict["accepted"] else "OBSERVED TRACE REJECTED")
            return 0 if verdict["accepted"] else 1
        from morph_x_multireplay import compile_and_verify_multi
        capture_check = None
        if args.capture is not None:
            frame = json.loads(args.capture.read_text(encoding="utf-8"))
            capture_check = compare_capture_to_spec(frame, spec)
        ir = spec_to_ir(spec)
        result = compile_and_verify_multi(ir)
        out = args.output_dir
        _write_json(out / "challenge.spec.json", spec)
        _write_json(out / "challenge.ir.json", ir)
        _write_json(out / "challenge.model-report.json", result["report"])
        (out / "challenge.morph").write_text(result["assembly"], encoding="utf-8")
        (out / "challenge.hex").write_text(result["hex"], encoding="utf-8")
        _write_json(out / "challenge.provenance.json", {
            "schema": "morph-x.protocol-zero.provenance.v1",
            "challenge_sha256": digest(spec),
            "compiler_model_report_sha256": digest(result["report"]),
            "source_capture_check": capture_check,
            "independent_observed_trace_available": False,
            "external_blind_challenge_verified": False,
            "notice": "MODEL VALIDATION ONLY; run a separate RTL/gate-level/physical observation and judge",
        })
        print(f"V2 MODEL-VERIFIED FIRMWARE: {result['report']['instruction_count']} words")
        print("NOT YET AN INDEPENDENT PROTOCOL ZERO PASS")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
