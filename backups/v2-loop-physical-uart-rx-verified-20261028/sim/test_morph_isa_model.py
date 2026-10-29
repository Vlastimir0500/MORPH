import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "compiler"))

from morph_assembler import assemble
from morph_isa_model import MorphISAModel


class MorphISAModelTests(unittest.TestCase):
    def make_model(self, source):
        model = MorphISAModel()
        model.load_program(assemble(source))
        model.step(rst_n=False)
        return model

    def test_drive_executes_encoded_instruction(self):
        model = self.make_model("DRIVE 1\nDRIVE 0")

        model.step()
        high = model.step()
        self.assertEqual(high.pin_out, 1)
        self.assertEqual(high.executed, "DRIVE")

        model.step()
        low = model.step()
        self.assertEqual(low.pin_out, 0)
        self.assertEqual(low.executed, "DRIVE")

    def test_wait_then_drive(self):
        model = self.make_model("WAIT 2\nDRIVE 1")

        model.step()
        model.step()
        self.assertEqual(model.wait_count, 2)

        model.step()
        self.assertEqual(model.wait_count, 1)

        model.step()
        self.assertEqual(model.wait_count, 0)
        self.assertEqual(model.pc, 1)

        model.step()
        result = model.step()
        self.assertEqual(result.pin_out, 1)

    def test_edge_wait_then_drive(self):
        model = self.make_model("EDGE RISE\nDRIVE 1")

        model.step(pin_in=0)
        model.step(pin_in=0)
        self.assertEqual(model.state, "EDGE_WAIT")

        waiting = model.step(pin_in=0)
        self.assertEqual(waiting.state, "EDGE_WAIT")

        model.step(pin_in=1)
        self.assertEqual(model.state, "FETCH")
        self.assertEqual(model.pc, 1)

        model.step(pin_in=1)
        result = model.step(pin_in=1)
        self.assertEqual(result.pin_out, 1)

    def test_sample_then_shift(self):
        model = self.make_model("SAMPLE\nSHIFT")

        model.step()
        sample = model.step(pin_in=1)
        self.assertEqual(sample.sample_reg, 1)

        model.step(pin_in=1)
        shifted = model.step(pin_in=1)
        self.assertEqual(shifted.shift_reg, 1)

    def test_branch_uses_four_bit_target(self):
        model = self.make_model("BRANCH target\nDRIVE 0\ntarget: DRIVE 1")

        model.step()
        branched = model.step()
        self.assertEqual(branched.pc, 2)
        self.assertEqual(branched.executed, "BRANCH")

        model.step()
        result = model.step()
        self.assertEqual(result.pin_out, 1)

    def test_reset_clears_registers_but_preserves_loaded_program(self):
        model = self.make_model("DRIVE 1")
        model.step()
        model.step()
        self.assertEqual(model.pin_out, 1)

        model.step(rst_n=False)

        self.assertEqual(model.pc, 0)
        self.assertEqual(model.pin_out, 0)
        self.assertEqual(model.state, "FETCH")
        self.assertEqual(model.memory[0], 0x1001)

    def test_invalid_program_word_width_rejected(self):
        model = MorphISAModel()

        with self.assertRaises(ValueError):
            model.load_program([0x10000])

    def test_program_depth_enforced(self):
        model = MorphISAModel()

        with self.assertRaises(ValueError):
            model.load_program([0x2000] * 17)


if __name__ == "__main__":
    unittest.main(verbosity=2)
