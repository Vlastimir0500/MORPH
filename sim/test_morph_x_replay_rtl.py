"""MORPH X generated-replay differential tests against the production V2 RTL.

Executed as part of `python -m pytest -q sim`; Verilator is mandatory for this
release gate. This invokes the existing V2 cycle-by-cycle RTL comparator.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
sys.path.insert(0, str(ROOT / "sim"))

from morph_assembler_v2 import assemble
from morph_x_replay import SCHEMA, capture_to_ir, compile_and_verify
import test_morph_rtl_diff_v2 as rtl_diff


@pytest.fixture(scope="module")
def rtl_harness():
    if shutil.which("verilator") is None:
        pytest.fail("MORPH X replay-to-RTL gate requires Verilator; do not skip RTL evidence")
    # Reuse the established cycle-by-cycle comparison code, without modifying
    # the verified V2 core, testbench or simulator model.
    rtl_diff.RTLComparisonV2Tests.setUpClass()
    return rtl_diff.RTLComparisonV2Tests(methodName="test_drive_wait_release_halt")


def require_rtl_matches_ir(rtl_harness, ir):
    result = compile_and_verify(ir)
    source = result["assembly"]
    words = assemble(source)
    report = result["report"]
    assert report["verification"]["model_verified"] is True
    assert len(words) == report["instruction_count"]
    assert [int(x, 16) for x in result["hex"].splitlines()] == words
    # The existing comparator checks each sampled cycle of the RTL trace:
    # controller state, PC, IR, driven pins, OE, sample, shift, waits, timeout,
    # fault, against the independent software model.
    halt_cycle = report["verification"]["halt_model_cycle"]
    model = rtl_harness.run_diff_words(words, [0] * (halt_cycle + 4))
    assert model.state == "HALT"
    assert model.pin_oe == 0
    assert not model.fault
    return report


def test_captured_fixture_compiles_to_rtl_equivalent_replay(rtl_harness):
    raw = json.loads((ROOT / "examples" / "morph_x_replay_capture.json").read_text())
    ir = capture_to_ir(raw, pin=0)
    report = require_rtl_matches_ir(rtl_harness, ir)
    assert report["expected_relative_cycles"] == [
        {"cycle": 0, "value": 1},
        {"cycle": 6, "value": 0},
        {"cycle": 12, "value": 1},
    ]


@pytest.mark.parametrize("pin,cycles", [
    (3, [0, 4, 10]),
    (7, [0, 2, 8, 14]),
])
def test_generated_replay_other_pins_and_gaps_match_rtl(rtl_harness, pin, cycles):
    ir = {
        "schema": SCHEMA,
        "clock_hz": 50_000_000,
        "pin": pin,
        "events": [
            {"cycle": cycle, "value": 1 if i % 2 == 0 else 0}
            for i, cycle in enumerate(cycles)
        ],
    }
    report = require_rtl_matches_ir(rtl_harness, ir)
    assert [event["cycle"] for event in report["expected_relative_cycles"]] == cycles
