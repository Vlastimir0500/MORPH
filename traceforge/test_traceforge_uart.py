import unittest

from traceforge_uart import (
    PAYLOAD,
    build_frame,
    mutate_bad_start,
    mutate_bad_stop,
    mutate_short_start,
    validate_trace,
)


class TraceforgeUARTTests(unittest.TestCase):
    def setUp(self):
        self.baseline = build_frame(PAYLOAD)

    def test_valid_a6_frame(self):
        result = validate_trace(self.baseline)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["decoded_payload"], "0xA6")
        self.assertEqual(result["start_sample"], 0)
        self.assertEqual(result["stop_sample"], 1)

    def test_bad_start_is_rejected(self):
        result = validate_trace(mutate_bad_start(self.baseline))
        self.assertFalse(result["valid"])
        self.assertIn("start_bit", [error["code"] for error in result["errors"]])

    def test_bad_stop_is_rejected(self):
        result = validate_trace(mutate_bad_stop(self.baseline))
        self.assertFalse(result["valid"])
        self.assertIn("stop_bit", [error["code"] for error in result["errors"]])

    def test_shortened_start_is_rejected(self):
        result = validate_trace(mutate_short_start(self.baseline))
        self.assertFalse(result["valid"])
        self.assertIn("waveform_length", [error["code"] for error in result["errors"]])

    def test_data_is_sampled_lsb_first(self):
        for payload in (0x00, 0xFF, 0x55, 0x3C, 0x81, 0x7E, 0xA5):
            with self.subTest(payload=payload):
                result = validate_trace(build_frame(payload))
                self.assertTrue(result["valid"], result["errors"])
                self.assertEqual(result["decoded_payload"], f"0x{payload:02X}")


if __name__ == "__main__":
    unittest.main()
