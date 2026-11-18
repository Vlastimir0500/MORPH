"""MORPH X M4: generated multi-pin firmware vs production V2 RTL per cycle."""
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
from morph_x_multireplay import capture_to_multi_ir, compile_and_verify_multi
import test_morph_rtl_diff_v2 as rtl_diff


@pytest.fixture(scope="module")
def rtl_harness():
    if shutil.which("verilator") is None:
        pytest.fail("MORPH X M4 RTL comparison requires Verilator")
    rtl_diff.RTLComparisonV2Tests.setUpClass()
    return rtl_diff.RTLComparisonV2Tests(methodName="test_drive_wait_release_halt")


@pytest.mark.parametrize("kind", ["capture", "spi"])
def test_multipin_generated_firmware_matches_every_rtl_cycle(rtl_harness, kind):
    if kind == "capture":
        path = ROOT / "examples/morph_x_multipin_capture.json"
        ir = capture_to_multi_ir(json.loads(path.read_text()), [0, 1])
    else:
        path = ROOT / "examples/morph_x_spi_two_bit_ir.json"
        ir = json.loads(path.read_text())
    result = compile_and_verify_multi(ir)
    words = assemble(result["assembly"])
    assert [int(w, 16) for w in result["hex"].splitlines()] == words
    assert result["report"]["verification"]["model_verified"]
    halt_cycle = result["report"]["verification"]["halt_model_cycle"]
    actual_model = rtl_harness.run_diff_words(words, [0] * (halt_cycle + 4))
    assert actual_model.state == "HALT"
    assert actual_model.pin_oe == 0
    assert not actual_model.fault
