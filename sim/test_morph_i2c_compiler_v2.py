import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
from morph_assembler_v2 import assemble
from morph_i2c_write_v2 import build_program
from morph_isa_model_v2 import MorphISAModelV2


class I2CCompilerV2Tests(unittest.TestCase):
    def test_two_arbitrary_data_bytes_fit_program_memory(self):
        source, words = build_program(0x50, [0xA5, 0x3C])
        self.assertEqual(len(words), 56)
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



    def _simulate_i2c_write(self, nack_sample=None):
        _, words = build_program(0x50, [0xA5, 0x3C])
        self.assertLessEqual(len(words), 64)

        # Discover SAMPLE cycles using an all-zero input trace.
        probe = MorphISAModelV2()
        probe.load_program(words)
        sample_cycles = []

        for cycle in range(5000):
            if probe.state == "EXEC" and (probe.ir >> 12) == 0x2:
                sample_cycles.append(cycle)

            snapshot = probe.step(pin_in=0)
            if snapshot.state == "HALT":
                break
        else:
            self.fail("I2C probe program did not halt within 5000 cycles")

        expected_samples = 3 if nack_sample is None else nack_sample
        scheduled_inputs = {}

        if nack_sample is not None:
            if not 1 <= nack_sample <= len(sample_cycles):
                self.fail(f"Invalid NACK sample index: {nack_sample}")

            # A pin value supplied two steps before SAMPLE reaches pin_sync_2
            # in time for that SAMPLE instruction.
            drive_cycle = sample_cycles[nack_sample - 1] - 2
            if drive_cycle < 0:
                self.fail("Cannot schedule NACK two cycles before SAMPLE")

            scheduled_inputs[drive_cycle] = 1 << 1

        # Replay with the scheduled NACK input.
        model = MorphISAModelV2()
        model.load_program(words)
        snapshots = []
        sample_count = 0

        for cycle in range(5000):
            pin_in = scheduled_inputs.get(cycle, 0)

            if model.state == "EXEC" and (model.ir >> 12) == 0x2:
                sample_count += 1

            snapshot = model.step(pin_in=pin_in)
            snapshots.append(snapshot)

            if snapshot.state == "HALT":
                break
        else:
            self.fail("I2C program did not halt within 5000 cycles")

        self.assertEqual(sample_count, expected_samples)
        self.assertFalse(model.fault)
        return model, snapshots, sample_count
    def _assert_explicit_stop(self, snapshots):
        stop_drives = [
            i for i, s in enumerate(snapshots)
            if s.executed == "DRIVE" and s.instruction == 0x1100
        ]
        self.assertTrue(stop_drives, "SDA-low STOP phase missing")
        start = stop_drives[-1]

        scl_release = next(
            (i for i in range(start + 1, len(snapshots))
             if snapshots[i].executed == "RELEASE"
             and snapshots[i].instruction == 0x7200),
            None,
        )
        self.assertIsNotNone(scl_release, "STOP did not release SCL")

        sda_release = next(
            (i for i in range(scl_release + 1, len(snapshots))
             if snapshots[i].executed == "RELEASE"
             and snapshots[i].instruction == 0x7100),
            None,
        )
        self.assertIsNotNone(sda_release, "STOP did not release SDA")

        sda = 1 << 1
        scl = 1 << 2

        self.assertTrue(snapshots[start].pin_oe & sda)
        self.assertEqual(snapshots[start].pin_out & sda, 0)

        self.assertTrue(snapshots[scl_release].pin_oe & sda)
        self.assertFalse(snapshots[scl_release].pin_oe & scl)

        self.assertFalse(snapshots[sda_release].pin_oe & sda)
        self.assertFalse(snapshots[sda_release].pin_oe & scl)

    def test_ack_path_generates_explicit_stop(self):
        model, snapshots, samples = self._simulate_i2c_write()
        self.assertEqual(samples, 3)
        self._assert_explicit_stop(snapshots)
        self.assertEqual(model.pin_oe, 0)

    def test_nack_path_preserves_error_flag_and_generates_stop(self):
        model, snapshots, samples = self._simulate_i2c_write(nack_sample=2)
        self.assertEqual(samples, 2)

        nack_events = [
            s for s in snapshots
            if s.executed == "DRIVE" and s.instruction == 0x1701
        ]
        self.assertTrue(nack_events, "NACK indicator was not asserted")
        self.assertTrue(nack_events[-1].pin_oe & (1 << 7))
        self.assertTrue(nack_events[-1].pin_out & (1 << 7))

        self._assert_explicit_stop(snapshots)
        self.assertEqual(model.pin_oe, 1 << 7)
        self.assertTrue(model.pin_out & (1 << 7))

if __name__ == "__main__":
    unittest.main()
