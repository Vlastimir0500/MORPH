"""Host replay compiler tests against the existing V2 assembler and model."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
from morph_x_replay import (
    ReplayError, capture_to_ir, compile_and_verify, compile_ir, validate_ir,
    verify_with_model, wait_instructions, SCHEMA,
)


def ir(*cycles, pin=0):
    return {"schema": SCHEMA, "clock_hz": 50_000_000, "pin": pin,
            "events": [{"cycle": cycle, "value": 1 - (i % 2)} for i, cycle in enumerate(cycles)]}


def frame(gaps=(6, 6), start=7):
    times = [start]
    for gap in gaps:
        times.append((times[-1] + gap) & 0xFFFF)
    assert len(times) <= 8
    slots = [[(1 if i % 2 == 0 else 0), 1, t & 255, t >> 8]
             for i, t in enumerate(times)]
    return {"status": 0x40 | len(times), "slots": slots}


def test_roundtrip_capture_to_typed_ir_and_firmware():
    source = frame()
    parsed = capture_to_ir(source, 0)
    assert parsed == ir(0, 6, 12)
    result = compile_and_verify(parsed)
    assert result["assembly"] == (
        "DRIVE 0, 1\nWAIT 2\nDRIVE 0, 0\nWAIT 2\nDRIVE 0, 1\nRELEASE 0\nHALT\n"
    )
    assert result["report"]["verification"]["observed"] == parsed["events"]
    assert result["report"]["verification"]["released_before_halt"]


@pytest.mark.parametrize("gap,commands", [
    (2, []), (4, ["WAIT 0"]), (5, ["WAIT 1"]),
    (6, ["WAIT 2"]), (259, ["WAIT 255"]),
    (260, ["WAIT 254", "WAIT 0"]),
    (261, ["WAIT 255", "WAIT 0"]),
    (516, ["WAIT 255", "WAIT 255"]),
])
def test_exact_instruction_gap(gap, commands):
    assert wait_instructions(gap) == commands
    result = compile_and_verify(ir(0, gap))
    assert result["report"]["verification"]["model_verified"]


@pytest.mark.parametrize("gap", [1, 3])
def test_reject_unrepresentable_gap(gap):
    with pytest.raises(ReplayError, match="unrepresentable"):
        compile_ir(ir(0, gap))


def test_counter_wrap_reproduces_modulo_gap():
    source = frame((4, 6), start=65534)
    assert [e["cycle"] for e in capture_to_ir(source, 0)["events"]] == [0, 4, 10]
    assert compile_and_verify(capture_to_ir(source, 0))["report"]["verification"]["model_verified"]


def test_capture_overflow_fails_closed():
    source = frame()
    source["status"] |= 0x10
    with pytest.raises(ReplayError, match="overflow"):
        capture_to_ir(source, 0)


def test_missing_selected_pin():
    source = frame()
    with pytest.raises(ReplayError, match="no captured transitions"):
        capture_to_ir(source, 3)


def test_inconsistent_changed_mask_fails_closed():
    source = frame()
    source["slots"][1][1] = 2
    with pytest.raises(ReplayError, match="inconsistent"):
        capture_to_ir(source, 0)


def test_multichannel_capture_selects_pin_without_inventing_timing():
    source = {"status": 0x43, "slots": [[1, 1, 4, 0], [3, 2, 6, 0], [2, 1, 11, 0]]}
    parsed = capture_to_ir(source, 0)
    assert parsed["events"] == [{"cycle": 0, "value": 1}, {"cycle": 7, "value": 0}]
    assert compile_and_verify(parsed)["report"]["verification"]["model_verified"]


def test_too_many_program_words_fails_closed():
    with pytest.raises(ReplayError, match="64"):
        compile_ir(ir(0, 20000))


def test_strict_ir_fields_and_cycle_values():
    candidate = ir(0, 6)
    candidate["unsupported"] = True
    with pytest.raises(ReplayError, match="exactly"):
        validate_ir(candidate)
    candidate = ir(0, 6)
    candidate["events"][1]["cycle"] = True
    with pytest.raises(ReplayError, match="integer"):
        validate_ir(candidate)
    candidate = ir(0, 6)
    candidate["events"][1]["value"] = 1
    with pytest.raises(ReplayError, match="identical"):
        validate_ir(candidate)


def test_mutation_negative_control_detects_timing_drift():
    candidate = ir(0, 6)
    source, words = compile_ir(candidate)
    assert "WAIT 2" in source
    bad_words = words[:]
    bad_words[1] = 0x3001
    with pytest.raises(ReplayError, match="timing mismatch"):
        verify_with_model(candidate, bad_words)


def test_all_eight_pin_indices_supported():
    for pin in range(8):
        outcome = compile_and_verify(ir(0, 4, 10, pin=pin))
        assert outcome["report"]["selected_pin"] == pin


def test_long_valid_schedule_within_64_word_limit():
    outcome = compile_and_verify(ir(0, 6000))
    assert outcome["report"]["instruction_count"] <= 64
