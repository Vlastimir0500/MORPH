import sys
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "compiler")
)

from morph_assembler import AssemblyError, assemble, disassemble


PROGRAM = """\
start:
    EDGE RISE
    DRIVE 1
    WAIT 4
    SAMPLE
    SHIFT
    DRIVE 0
    BRANCH start
"""


class AssemblerTests(unittest.TestCase):
    def test_expected_instruction_words(self):
        self.assertEqual(
            assemble(PROGRAM),
            [0x4001, 0x1001, 0x3004, 0x2000,
             0x5000, 0x1000, 0x6000],
        )

    def test_disassemble_expected_words(self):
        self.assertEqual(
            disassemble(
                [0x4001, 0x1001, 0x3004, 0x2000,
                 0x5000, 0x1000, 0x6000]
            ),
            [
                "EDGE RISE",
                "DRIVE 1",
                "WAIT 4",
                "SAMPLE",
                "SHIFT",
                "DRIVE 0",
                "BRANCH 0",
            ],
        )

    def test_round_trip(self):
        words = assemble(PROGRAM)
        self.assertEqual(assemble("\n".join(disassemble(words))), words)

    def test_inline_label_and_hex_wait(self):
        self.assertEqual(
            assemble("loop: WAIT 0x10\nBRANCH loop"),
            [0x3010, 0x6000],
        )

    def test_comments_and_blank_lines(self):
        source = "; initial comment\n\nstart: DRIVE 1 # comment\nBRANCH start\n"
        self.assertEqual(assemble(source), [0x1001, 0x6000])

    def test_unknown_instruction_rejected(self):
        with self.assertRaises(AssemblyError):
            assemble("NOP")

    def test_invalid_operands_rejected(self):
        bad_sources = [
            "DRIVE 2",
            "WAIT 256",
            "WAIT -1",
            "EDGE UP",
            "SAMPLE 1",
            "SHIFT 1",
            "BRANCH nowhere",
        ]
        for source in bad_sources:
            with self.subTest(source=source):
                with self.assertRaises(AssemblyError):
                    assemble(source)

    def test_program_depth_limit(self):
        source = "\n".join(["SAMPLE"] * 17)
        with self.assertRaises(AssemblyError):
            assemble(source)

    def test_duplicate_label_rejected(self):
        with self.assertRaises(AssemblyError):
            assemble("loop: SAMPLE\nloop: SHIFT")

    def test_invalid_machine_words_rejected(self):
        for word in (0x0000, 0x7000, 0x1102, 0x2001, 0x4002, 0x5001, 0x6010):
            with self.subTest(word=hex(word)):
                with self.assertRaises(AssemblyError):
                    disassemble([word])


if __name__ == "__main__":
    unittest.main(verbosity=2)
