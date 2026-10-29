import random
import unittest

from morph_model import Action, Event, MachineModel, Transition, PIN_MASK, TIMER_MAX


class RandomizedSafetyTests(unittest.TestCase):
    def test_random_cycles_preserve_machine_invariants(self):
        rng = random.Random(20261011)

        model = MachineModel(
            [
                Transition(
                    state=0,
                    require_events=Event.EXTERNAL,
                    next_state=1,
                    action=Action(
                        data_mask=0b11,
                        data_value=0,
                        oe_mask=0b11,
                        oe_value=0b11,
                        wait_cycles=7,
                    ),
                    name="drive_low",
                ),
                Transition(
                    state=1,
                    require_events=Event.EXTERNAL,
                    next_state=0,
                    action=Action(
                        oe_mask=0b11,
                        oe_value=0,
                        wait_cycles=0,
                    ),
                    name="release",
                ),
            ],
            state_count=2,
            reset_state=0,
            open_drain_mask=0b11,
        )

        checked_cycles = 0

        for _ in range(5000):
            raw_pins = rng.randint(0, PIN_MASK)
            rst_n = rng.random() > 0.015
            external_events = Event.NONE

            if rng.random() < 0.15:
                external_events |= Event.EXTERNAL
            if rng.random() < 0.10:
                external_events |= Event.RX_READY

            prior_wait = model.wait_remaining
            result = model.step(
                raw_pins=raw_pins,
                external_events=external_events,
                rst_n=rst_n,
            )

            self.assertGreaterEqual(result.state_after, 0)
            self.assertLess(result.state_after, model.state_count)

            self.assertGreaterEqual(result.pin_data, 0)
            self.assertLessEqual(result.pin_data, PIN_MASK)
            self.assertGreaterEqual(result.output_enable, 0)
            self.assertLessEqual(result.output_enable, PIN_MASK)

            self.assertGreaterEqual(result.wait_remaining, 0)
            self.assertLessEqual(result.wait_remaining, TIMER_MAX)

            self.assertEqual(
                bool(result.events & Event.RISE),
                bool(result.rising_pins),
            )
            self.assertEqual(
                bool(result.events & Event.FALL),
                bool(result.falling_pins),
            )

            if rst_n:
                self.assertEqual(
                    bool(result.events & Event.TIMEOUT),
                    prior_wait == 1,
                )
            else:
                self.assertEqual(result.events, Event.NONE)
                self.assertEqual(result.output_enable, 0)
                self.assertIsNone(result.fault)

            if result.fault is not None:
                self.assertEqual(result.output_enable, 0)
            else:
                active_open_drain_high = (
                    result.pin_data
                    & result.output_enable
                    & model.open_drain_mask
                )
                self.assertEqual(active_open_drain_high, 0)

            checked_cycles += 1

        self.assertEqual(checked_cycles, 5000)
        print(f"PASS: {checked_cycles} randomized safety cycles")


if __name__ == "__main__":
    unittest.main(verbosity=2)
