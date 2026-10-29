import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
from morph_assembler_v2 import AssemblyError, assemble, disassemble


class AssemblerV2Tests(unittest.TestCase):
    def test_expected_encodings(self):
        source = """
        DRIVE 3, 1
        SAMPLE 5
        WAIT 15
        EDGE 2, RISE, 7
        SHIFT
        RELEASE 3
        HALT
        """
        self.assertEqual(
            assemble(source),
            [0x1301, 0x2500, 0x300F, 0x420F, 0x5000, 0x7300, 0x0000],
        )

    def test_labels_and_conditional_branch(self):
        source = """
        SAMPLE 5
        BRANCH_SAMPLE 1, high
        DRIVE 1, 1
        high: DRIVE 2, 1
        HALT
        """
        self.assertEqual(assemble(source), [0x2500, 0x8083, 0x1101, 0x1201, 0x0000])

    def test_full_round_trip(self):
        source = """
        top: DRIVE 0, 1
        SAMPLE 7
        WAIT 255
        EDGE 7, FALL, 127
        SHIFT
        BRANCH top
        RELEASE 0
        BRANCH_SAMPLE 0, top
        HALT
        """
        words = assemble(source)
        self.assertEqual(assemble("\n".join(disassemble(words))), words)

    def test_edge_without_timeout_means_forever(self):
        self.assertEqual(assemble("EDGE 4, FALL"), [0x4400])
        self.assertEqual(assemble("EDGE 4, RISE, FOREVER"), [0x4401])

    def test_inline_label_comments_and_hex(self):
        self.assertEqual(
            assemble("again: WAIT 0x10 ; delay\nBRANCH again # loop"),
            [0x3010, 0x6000],
        )

    def test_all_pin_numbers(self):
        for pin in range(8):
            self.assertEqual(assemble(f"DRIVE {pin}, 1"), [0x1001 | (pin << 8)])
            self.assertEqual(assemble(f"SAMPLE {pin}"), [0x2000 | (pin << 8)])
            self.assertEqual(assemble(f"RELEASE {pin}"), [0x7000 | (pin << 8)])

    def test_bad_pin_rejected(self):
        for source in ("DRIVE 8, 1", "SAMPLE -1", "RELEASE 9", "EDGE 8, RISE"):
            with self.subTest(source=source), self.assertRaises(AssemblyError):
                assemble(source)

    def test_bad_drive_value_rejected(self):
        with self.assertRaises(AssemblyError):
            assemble("DRIVE 0, 2")

    def test_bad_wait_rejected(self):
        with self.assertRaises(AssemblyError):
            assemble("WAIT 256")

    def test_edge_timeout_range(self):
        with self.assertRaises(AssemblyError):
            assemble("EDGE 0, RISE, 128")

    def test_invalid_direction_rejected(self):
        with self.assertRaises(AssemblyError):
            assemble("EDGE 0, UP")

    def test_missing_and_extra_operands_rejected(self):
        for source in ("DRIVE 1", "SAMPLE", "WAIT", "SHIFT 1", "HALT 0", "RELEASE"):
            with self.subTest(source=source), self.assertRaises(AssemblyError):
                assemble(source)

    def test_duplicate_label_rejected(self):
        with self.assertRaises(AssemblyError):
            assemble("loop: WAIT 1\nloop: HALT")

    def test_branch_target_validation(self):
        for source in ("BRANCH 1", "BRANCH_SAMPLE 1, 4", "BRANCH missing"):
            with self.subTest(source=source), self.assertRaises(AssemblyError):
                assemble(source)

    def test_depth_limit(self):
        self.assertEqual(len(assemble("\n".join(["HALT"] * 64))), 64)
        with self.assertRaises(AssemblyError):
            assemble("\n".join(["HALT"] * 65))

    def test_disassembler_rejects_invalid_encoding(self):
        for word in (0x1002, 0x2800, 0x6100, 0x7001, 0x8040, 0x9000):
            with self.subTest(word=hex(word)), self.assertRaises(AssemblyError):
                disassemble([word])


if __name__ == "__main__":
    unittest.main()
