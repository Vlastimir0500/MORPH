import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
from morph_assembler_v2 import assemble
from morph_spi_tx_v2 import build_program


class SPITxV2Tests(unittest.TestCase):
    def test_modes_compile_to_compact_programs(self):
        for mode in (1, 2, 3):
            with self.subTest(mode=mode):
                source, words = build_program(mode, 0xA5)
                self.assertEqual(len(words), 11)
                self.assertEqual(assemble(source), words)
                self.assertEqual(words[2], 0xA0A5)

    def test_mode_clock_polarity_and_phase(self):
        expected = {1: (0, 1), 2: (1, 0), 3: (1, 1)}
        for mode, (cpol, cpha) in expected.items():
            with self.subTest(mode=mode):
                source, _ = build_program(mode, 0x5A)
                self.assertIn(f"DRIVE 2, {cpol}", source)
                if cpha == 0:
                    self.assertLess(source.index("DRIVE_SHIFT 1"), source.index(f"DRIVE 2, {1-cpol}"))
                else:
                    self.assertLess(source.index(f"DRIVE 2, {1-cpol}"), source.index("DRIVE_SHIFT 1"))

    def test_all_payload_values_are_encoded(self):
        for value in (0x00, 0x01, 0x55, 0x80, 0xFF):
            with self.subTest(value=value):
                _, words = build_program(3, value)
                self.assertEqual(words[2], 0xA000 | value)

    def test_invalid_modes_rejected(self):
        for mode in (-1, 4, 8):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                build_program(mode, 0xA5)

    def test_invalid_payload_rejected(self):
        for value in (-1, 0x100):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_program(1, value)

    def test_invalid_half_period_rejected(self):
        for period in (0, 256):
            with self.subTest(period=period), self.assertRaises(ValueError):
                build_program(1, 0xA5, period)


if __name__ == "__main__":
    unittest.main()
