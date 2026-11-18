"""MORPH X M4 strict multi-pin Temporal IR / schedule qualification."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
from morph_assembler_v2 import assemble
from morph_x_multireplay import (
    SCHEMA, ReplayError, capture_to_multi_ir, compile_and_verify_multi,
    compile_multi_ir, validate_multi_ir, verify_multi_model,
)

CAPTURE = ROOT / "examples" / "morph_x_multipin_capture.json"
SPI = ROOT / "examples" / "morph_x_spi_two_bit_ir.json"


def fixture_ir():
    return capture_to_multi_ir(json.loads(CAPTURE.read_text()), [0, 1])


def test_full_eight_event_capture_round_trip():
    ir = fixture_ir()
    assert ir["pins"] == [0, 1]
    assert ir["events"] == [
        {"cycle": i * 6, "pin": i % 2, "value": 1 if i < 2 or 4 <= i < 6 else 0}
        for i in range(8)
    ]
    result = compile_and_verify_multi(ir)
    assert result["report"]["verification"]["model_verified"]
    assert result["report"]["verification"]["all_pins_released"]
    assert result["report"]["instruction_count"] == 18
    assert result["assembly"].endswith("RELEASE 0\nRELEASE 1\nHALT\n")


def test_protocol_spi_two_bit_pin_choreography():
    ir = json.loads(SPI.read_text())
    result = compile_and_verify_multi(ir)
    assert result["report"]["verification"]["model_verified"]
    assert len(ir["events"]) == 8
    assert result["report"]["instruction_count"] == 19
    assert [x["pin"] for x in ir["events"]] == [2, 1, 0, 0, 1, 0, 0, 2]


def test_deterministic_hex_and_provenance():
    first = compile_and_verify_multi(fixture_ir())
    second = compile_and_verify_multi(fixture_ir())
    assert first == second
    assert len(first["report"]["ir_sha256"]) == 64
    assert len(first["report"]["program_sha256"]) == 64
    assert len(assemble(first["assembly"])) == first["report"]["instruction_count"]


@pytest.mark.parametrize("gap", [2, 4, 5, 6, 10, 259, 260, 516])
def test_valid_interpin_exact_gaps(gap):
    ir = {"schema": SCHEMA, "clock_hz": 50_000_000, "pins": [0, 1],
          "events": [{"cycle": 0, "pin": 0, "value": 1},
                     {"cycle": gap, "pin": 1, "value": 1}]}
    assert compile_and_verify_multi(ir)["report"]["verification"]["model_verified"]


@pytest.mark.parametrize("gap", [1, 3])
def test_reject_unrepresentable_gap(gap):
    ir = {"schema": SCHEMA, "clock_hz": 50_000_000, "pins": [0, 1],
          "events": [{"cycle": 0, "pin": 0, "value": 1},
                     {"cycle": gap, "pin": 1, "value": 1}]}
    with pytest.raises(ReplayError, match="unrepresentable"):
        compile_multi_ir(ir)


def test_simultaneous_input_changes_fail_closed():
    frame = {"status": 0x41, "slots": [[3, 3, 1, 0]]}
    with pytest.raises(ReplayError, match="simultaneous"):
        capture_to_multi_ir(frame, [0, 1])


def test_simultaneous_ir_events_fail_closed():
    ir = fixture_ir()
    ir["events"][1]["cycle"] = ir["events"][0]["cycle"]
    with pytest.raises(ReplayError, match="simultaneous"):
        validate_multi_ir(ir)


def test_capture_overflow_rejected():
    frame = json.loads(CAPTURE.read_text())
    frame["status"] |= 0x10
    with pytest.raises(ReplayError, match="overflow"):
        capture_to_multi_ir(frame, [0, 1])


def test_invalid_middle_mask_rejected():
    frame = json.loads(CAPTURE.read_text())
    frame["slots"][2][1] = 3
    with pytest.raises(ReplayError, match="inconsistent"):
        capture_to_multi_ir(frame, [0, 1])


def test_no_selected_pin_transition_rejected():
    with pytest.raises(ReplayError, match="no transitions"):
        capture_to_multi_ir(json.loads(CAPTURE.read_text()), [7])


def test_sorting_and_duplicate_pin_rules():
    for pins in [[1, 0], [0, 0], [0, 8], [True], []]:
        with pytest.raises(ReplayError):
            capture_to_multi_ir(json.loads(CAPTURE.read_text()), pins)


def test_unknown_fields_and_boolean_cycle_rejected():
    ir = fixture_ir()
    ir["events"][0]["cycle"] = True
    with pytest.raises(ReplayError, match="integer"):
        validate_multi_ir(ir)
    ir = fixture_ir()
    ir["unsafe"] = "ignored?"
    with pytest.raises(ReplayError, match="exactly"):
        validate_multi_ir(ir)


def test_missing_declared_pin_is_rejected():
    ir = fixture_ir()
    ir["pins"].append(2)
    with pytest.raises(ReplayError, match="each declared pin"):
        validate_multi_ir(ir)


def test_repeated_same_pin_level_rejected():
    ir = fixture_ir()
    ir["events"][2]["value"] = 1
    with pytest.raises(ReplayError, match="not a transition"):
        validate_multi_ir(ir)


def test_clock_mismatch_rejected():
    ir = fixture_ir()
    ir["clock_hz"] = 25_000_000
    with pytest.raises(ReplayError, match="clock_hz"):
        validate_multi_ir(ir)


def test_program_memory_limit_rejected():
    ir = {"schema": SCHEMA, "clock_hz": 50_000_000,
          "pins": [0, 1], "events": [
              {"cycle": i * 258, "pin": i % 2, "value": (i // 2) % 2}
              for i in range(35)
          ]}
    with pytest.raises(ReplayError, match="capacity"):
        compile_multi_ir(ir)


def test_counter_wrap_works_modulo_65536():
    frame = {"status": 0x42,
             "slots": [[1, 1, 254, 255], [3, 2, 4, 0]]}
    ir = capture_to_multi_ir(frame, [0, 1])
    assert ir["events"] == [
        {"cycle": 0, "pin": 0, "value": 1},
        {"cycle": 6, "pin": 1, "value": 1},
    ]
    assert compile_and_verify_multi(ir)["report"]["verification"]["model_verified"]


def test_unselected_pin_transitions_are_filtered_without_retiming():
    frame = {"status": 0x43,
             "slots": [[1, 1, 10, 0], [5, 4, 13, 0], [4, 1, 18, 0]]}
    ir = capture_to_multi_ir(frame, [0])
    assert ir["events"] == [
        {"cycle": 0, "pin": 0, "value": 1},
        {"cycle": 8, "pin": 0, "value": 0},
    ]
    assert compile_and_verify_multi(ir)["report"]["verification"]["model_verified"]


def test_reordered_events_rejected():
    ir = fixture_ir()
    ir["events"][2]["cycle"] = 1
    with pytest.raises(ReplayError, match="non-increasing"):
        validate_multi_ir(ir)


def test_mutation_changes_proven_timing():
    ir = fixture_ir()
    _, words = compile_multi_ir(ir)
    altered = words[:]
    # The first WAIT 2 becomes WAIT 1; this must break time equivalence.
    assert altered[1] == 0x3002
    altered[1] = 0x3001
    with pytest.raises(ReplayError, match="timing/value mismatch"):
        verify_multi_model(ir, altered)


def test_cli_capture_and_ir_emit_expected_firmware(tmp_path):
    for fixture, pins, expected in [
        (CAPTURE, ["--pins", "0", "1"], 18),
        (SPI, [], 19),
    ]:
        out = tmp_path / fixture.stem
        result = subprocess.run(
            [sys.executable, str(ROOT / "compiler" / "morph_x_multireplay.py"),
             str(fixture), *pins, "--output-dir", str(out)],
            text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads((out / "multi.report.json").read_text())
        assert report["instruction_count"] == expected
        assert report["verification"]["all_pins_released"]
        assert len((out / "multi.hex").read_text().splitlines()) == expected


def test_cli_mismatched_pins_fails_closed(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "compiler" / "morph_x_multireplay.py"),
         str(SPI), "--pins", "0", "1", "--output-dir", str(tmp_path)],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 2
    assert "does not match" in result.stderr
