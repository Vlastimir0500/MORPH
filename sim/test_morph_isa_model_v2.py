import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
sys.path.insert(0, str(ROOT / "sim"))
from morph_assembler_v2 import assemble
from morph_isa_model_v2 import MorphISAModelV2


class ISAModelV2Tests(unittest.TestCase):
    def make_model(self, source):
        model = MorphISAModelV2()
        model.load_program(assemble(source))
        model.step(rst_n=False)
        return model

    def run_cycles(self, model, count, pin=0):
        for _ in range(count):
            model.step(pin_in=pin)

    def test_drive_and_release_selected_pin(self):
        model = self.make_model("DRIVE 3, 1\nRELEASE 3\nHALT")
        self.run_cycles(model, 3)
        self.assertEqual(model.pin_out, 0x08)
        self.assertEqual(model.pin_oe, 0x08)
        self.run_cycles(model, 3)
        self.assertEqual(model.pin_oe, 0)
        self.assertEqual(model.pin_out, 0)

    def test_sample_selected_pin_and_shift(self):
        model = self.make_model("SAMPLE 5\nSHIFT\nHALT")
        self.run_cycles(model, 6, pin=0x20)
        self.assertEqual(model.sample_reg, 1)
        self.assertEqual(model.shift_reg, 1)

    def test_wait_completes(self):
        model = self.make_model("DRIVE 0, 1\nWAIT 3\nDRIVE 0, 0\nHALT")
        self.run_cycles(model, 7)
        self.assertEqual(model.pin_out & 1, 1)
        self.run_cycles(model, 6)
        self.assertEqual(model.pin_out & 1, 0)
        self.assertFalse(model.fault)

    def test_rising_edge_completes_without_fault(self):
        model = self.make_model("EDGE 2, RISE, 7\nDRIVE 4, 1\nHALT")
        for pin in (0, 0, 0, 0x04, 0x04, 0x04, 0x04):
            model.step(pin_in=pin)
        self.assertEqual(model.pin_oe & 0x10, 0x10)
        self.assertFalse(model.timed_out)
        self.assertFalse(model.fault)

    def test_falling_edge_completes(self):
        model = self.make_model("EDGE 1, FALL, 7\nDRIVE 6, 1\nHALT")
        for pin in (0x02, 0x02, 0x02, 0x00, 0x00, 0x00, 0x00):
            model.step(pin_in=pin)
        self.assertEqual(model.pin_oe & 0x40, 0x40)
        self.assertFalse(model.fault)

    def test_edge_timeout_halts_and_releases_all_pins(self):
        model = self.make_model("DRIVE 0, 1\nEDGE 2, RISE, 3\nDRIVE 4, 1\nHALT")
        self.run_cycles(model, 20)
        self.assertTrue(model.timed_out)
        self.assertTrue(model.fault)
        self.assertEqual(model.pin_oe, 0)
        self.assertEqual(model.state, "HALT")

    def test_zero_edge_timeout_waits_forever(self):
        model = self.make_model("EDGE 2, RISE\nHALT")
        self.run_cycles(model, 100)
        self.assertEqual(model.state, "EDGE_WAIT")
        self.assertFalse(model.timed_out)
        self.assertFalse(model.fault)

    def test_conditional_branch_taken(self):
        model = self.make_model(
            "SAMPLE 5\nBRANCH_SAMPLE 1, yes\nDRIVE 1, 1\nyes: DRIVE 2, 1\nHALT"
        )
        self.run_cycles(model, 14, pin=0x20)
        self.assertEqual(model.pin_oe & 0x04, 0x04)
        self.assertEqual(model.pin_oe & 0x02, 0)

    def test_conditional_branch_not_taken(self):
        model = self.make_model(
            "SAMPLE 5\nBRANCH_SAMPLE 1, yes\nDRIVE 1, 1\nyes: DRIVE 2, 1\nHALT"
        )
        self.run_cycles(model, 14, pin=0)
        self.assertEqual(model.pin_oe & 0x02, 0x02)
        self.assertEqual(model.pin_oe & 0x04, 0x04)

    def test_counted_loop_repeats_exactly(self):
        model = self.make_model("start: SAMPLE 0\nSHIFT\nLOOP 3, start\nHALT")
        self.run_cycles(model, 30, pin=0x01)
        self.assertEqual(model.shift_reg, 0x07)
        self.assertFalse(model.fault)
        self.assertEqual(model.state, "HALT")

    def test_counted_loop_one_pass_does_not_repeat(self):
        model = self.make_model("start: SAMPLE 0\nSHIFT\nLOOP 1, start\nHALT")
        self.run_cycles(model, 20, pin=0x01)
        self.assertEqual(model.shift_reg, 0x01)
        self.assertFalse(model.fault)
        self.assertEqual(model.state, "HALT")

    def test_invalid_counted_loop_faults_and_releases_outputs(self):
        model = MorphISAModelV2()
        model.load_program([0x1101, 0x9041])
        model.step(rst_n=False)
        self.run_cycles(model, 8)
        self.assertTrue(model.fault)
        self.assertEqual(model.pin_oe, 0)
        self.assertEqual(model.state, "HALT")

    def test_reset_clears_active_counted_loop(self):
        model = self.make_model("start: DRIVE 0, 1\nWAIT 1\nLOOP 5, start\nHALT")
        self.run_cycles(model, 8)
        self.assertTrue(model.loop_active)
        program = list(model.memory)
        model.step(rst_n=False, pin_in=0x20)
        self.assertFalse(model.loop_active)
        self.assertEqual(model.loop_remaining, 0)
        self.assertEqual(model.pc, 0)
        self.assertEqual(model.pin_oe, 0)
        self.assertEqual(model.state, "FETCH")
        self.assertEqual(model.memory, program)

    def test_invalid_opcode_faults_and_releases_outputs(self):
        model = MorphISAModelV2()
        model.load_program([0x1101, 0xA000])
        model.step(rst_n=False)
        self.run_cycles(model, 6)
        self.assertTrue(model.fault)
        self.assertEqual(model.pin_oe, 0)
        self.assertEqual(model.state, "HALT")

    def test_invalid_pin_selector_faults(self):
        model = MorphISAModelV2()
        model.load_program([0x1801])
        model.step(rst_n=False)
        self.run_cycles(model, 3)
        self.assertTrue(model.fault)
        self.assertEqual(model.pin_oe, 0)

    def test_reset_clears_runtime_state_preserves_program(self):
        model = self.make_model("DRIVE 3, 1\nHALT")
        self.run_cycles(model, 3)
        program = list(model.memory)
        model.step(rst_n=False, pin_in=0x20)
        self.assertEqual(model.memory, program)
        self.assertEqual(model.pin_out, 0)
        self.assertEqual(model.pin_oe, 0)
        self.assertEqual(model.pc, 0)
        self.assertEqual(model.state, "FETCH")
        self.assertEqual(model.pin_prev, 0x20)
        self.assertFalse(model.fault)
        self.assertFalse(model.timed_out)

    def test_program_mode_resets_execution_state(self):
        model = self.make_model("DRIVE 3, 1\nHALT")
        self.run_cycles(model, 3)
        model.step(pin_in=0x08, program_mode=True)
        self.assertEqual(model.pc, 0)
        self.assertEqual(model.pin_oe, 0)
        self.assertEqual(model.pin_prev, 0x08)

    def test_program_depth_enforced(self):
        model = MorphISAModelV2()
        with self.assertRaises(ValueError):
            model.load_program([0] * 65)

    def test_program_word_width_enforced(self):
        model = MorphISAModelV2()
        with self.assertRaises(ValueError):
            model.load_program([0x10000])


if __name__ == "__main__":
    unittest.main()
