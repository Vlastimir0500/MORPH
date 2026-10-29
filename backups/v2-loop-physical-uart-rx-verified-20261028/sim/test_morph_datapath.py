import random
import unittest

from morph_datapath import BoundedFIFO, ShiftRegister


class FIFOTests(unittest.TestCase):
    def test_fifo_order(self):
        fifo = BoundedFIFO(depth=2)
        fifo.tick(push_data=10)
        fifo.tick(push_data=20)

        first = fifo.tick(pop=True)
        second = fifo.tick(pop=True)

        self.assertEqual(first.popped_data, 10)
        self.assertEqual(second.popped_data, 20)
        self.assertTrue(fifo.empty)

    def test_full_fifo_rejects_extra_push(self):
        fifo = BoundedFIFO(depth=2)
        fifo.tick(push_data=1)
        fifo.tick(push_data=2)

        result = fifo.tick(push_data=3)

        self.assertTrue(result.overflow)
        self.assertFalse(result.push_accepted)
        self.assertEqual(result.level, 2)
        self.assertEqual(fifo.tick(pop=True).popped_data, 1)

    def test_full_fifo_allows_simultaneous_pop_push(self):
        fifo = BoundedFIFO(depth=2)
        fifo.tick(push_data=1)
        fifo.tick(push_data=2)

        result = fifo.tick(push_data=3, pop=True)

        self.assertEqual(result.popped_data, 1)
        self.assertTrue(result.pop_accepted)
        self.assertTrue(result.push_accepted)
        self.assertEqual(result.level, 2)
        self.assertEqual(fifo.tick(pop=True).popped_data, 2)
        self.assertEqual(fifo.tick(pop=True).popped_data, 3)

    def test_empty_simultaneous_push_pop_has_no_fallthrough(self):
        fifo = BoundedFIFO(depth=2)

        result = fifo.tick(push_data=7, pop=True)

        self.assertTrue(result.underflow)
        self.assertFalse(result.pop_accepted)
        self.assertTrue(result.push_accepted)
        self.assertEqual(result.level, 1)
        self.assertEqual(fifo.tick(pop=True).popped_data, 7)

    def test_invalid_fifo_data_rejected(self):
        fifo = BoundedFIFO(depth=2, width=8)

        with self.assertRaises(ValueError):
            fifo.tick(push_data=256)

    def test_random_fifo_operations(self):
        rng = random.Random(20261011)
        fifo = BoundedFIFO(depth=8)
        reference = []

        for _ in range(5000):
            do_push = rng.random() < 0.6
            do_pop = rng.random() < 0.5
            value = rng.randrange(256) if do_push else None

            expected_pop = reference.pop(0) if do_pop and reference else None
            expected_underflow = do_pop and expected_pop is None

            if do_push and len(reference) < fifo.depth - (1 if do_pop and expected_pop is not None else 0):
                expected_push = True
            elif do_push and do_pop and expected_pop is not None:
                expected_push = True
            else:
                expected_push = do_push and not do_pop and len(reference) < fifo.depth

            result = fifo.tick(push_data=value, pop=do_pop)

            if expected_push:
                reference.append(value)

            self.assertEqual(result.popped_data, expected_pop)
            self.assertEqual(result.underflow, expected_underflow)
            self.assertEqual(result.level, len(reference))
            self.assertLessEqual(result.level, fifo.depth)


class ShiftRegisterTests(unittest.TestCase):
    def test_load_and_left_shift(self):
        shift = ShiftRegister(width=8)
        shift.tick(load=0b10000001)

        result = shift.tick(shift_left=True, serial_in=1)

        self.assertEqual(result.shifted_out, 1)
        self.assertEqual(result.value, 0b00000011)

    def test_right_shift(self):
        shift = ShiftRegister(width=8, value=0b00000011)

        result = shift.tick(shift_right=True, serial_in=1)

        self.assertEqual(result.shifted_out, 1)
        self.assertEqual(result.value, 0b10000001)

    def test_clear_has_priority(self):
        shift = ShiftRegister(width=8, value=15)

        result = shift.tick(load=255, shift_left=True, clear=True)

        self.assertEqual(result.value, 0)
        self.assertIsNone(result.shifted_out)

    def test_conflicting_shifts_rejected(self):
        shift = ShiftRegister(width=8)

        with self.assertRaises(ValueError):
            shift.tick(shift_left=True, shift_right=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
