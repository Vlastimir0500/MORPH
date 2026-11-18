"""M5 new unfamiliar-pattern replay vs V2 production RTL, cycle by cycle."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
sys.path.insert(0, str(ROOT / "sim"))

from morph_assembler_v2 import assemble
from morph_x_multireplay import compile_and_verify_multi
from morph_x_protocol_zero import generate_selftest_spec, spec_to_ir
import test_morph_rtl_diff_v2 as rtl_diff


@pytest.fixture(scope="module")
def rtl_harness():
    if not shutil.which("verilator"):
        pytest.fail("M5 Protocol Zero RTL verification requires Verilator; no skip")
    rtl_diff.RTLComparisonV2Tests.setUpClass()
    return rtl_diff.RTLComparisonV2Tests(methodName="test_drive_wait_release_halt")


@pytest.mark.parametrize("seed", [0x5EED17, 0xB105D, 0x21])
def test_new_four_pin_challenge_matches_cycle_by_cycle_rtl(rtl_harness, seed):
    spec = generate_selftest_spec(seed)
    compiled = compile_and_verify_multi(spec_to_ir(spec))
    words = assemble(compiled["assembly"])
    assert [int(w, 16) for w in compiled["hex"].splitlines()] == words
    halt_cycle = compiled["report"]["verification"]["halt_model_cycle"]
    rtl_model = rtl_harness.run_diff_words(words, [0] * (halt_cycle + 4))
    assert rtl_model.state == "HALT"
    assert rtl_model.pin_oe == 0
    assert not rtl_model.fault
