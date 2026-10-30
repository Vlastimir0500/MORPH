import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
from morph_assembler_v2 import assemble
from morph_i2c_write_v2 import build_program


class I2CCompilerV2Tests(unittest.TestCase):
    def test_two_arbitrary_data_bytes_fit_program_memory(self):
        source, words = build_program(0x50, [0xA5, 0x3C])
        self.assertEqual(len(words), 58)
        self.assertEqual(assemble(source), words)
        immediates = [word & 0xFF for word in words if (word >> 12) == 0xA]
        self.assertEqual(immediates, [0xA0, 0xA5, 0x3C])

    def test_one_data_byte_program(self):
        source, words = build_program(0x50, [0x00])
        self.assertLessEqual(len(words), 64)
        self.assertEqual(assemble(source), words)

    def test_invalid_address_rejected(self):
        for address in (-1, 0x80, 128):
            with self.subTest(address=address), self.assertRaises(ValueError):
                build_program(address, [0xA5])

    def test_invalid_payload_rejected(self):
        for payload in ([], [0x100], [-1], [0x00, 0x01, 0x02]):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                build_program(0x50, payload)

    def test_invalid_half_period_rejected(self):
        for period in (0, 256):
            with self.subTest(period=period), self.assertRaises(ValueError):
                build_program(0x50, [0xA5], period)


if __name__ == "__main__":
    unittest.main()
