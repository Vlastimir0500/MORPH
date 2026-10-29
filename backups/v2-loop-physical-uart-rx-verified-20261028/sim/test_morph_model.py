import unittest

from morph_model import Action, Event, MachineModel, Transition


class MorphModelTests(unittest.TestCase):
    def test_two_stage_synchronization_and_rising_edge(self):
        model = MachineModel(
            [
                Transition(
                    state=0,
                    require_events=Event.RISE,
                    rise_mask=1,
                    next_state=1,
                    name="rising_edge",
                )
            ],
            state_count=2,
        )

        first = model.step(raw_pins=1)
        second = model.step(raw_pins=1)
        third = model.step(raw_pins=1)

        self.assertEqual(first.sampled_pins, 0)
        self.assertEqual(second.sampled_pins, 0)
        self.assertEqual(third.sampled_pins, 1)
        self.assertEqual(third.rising_pins, 1)
        self.assertEqual(third.state_after, 1)
        self.assertEqual(third.selected_transition, "rising_edge")

    def test_falling_edge_detection(self):
        model = MachineModel([], state_count=1)

        model.step(raw_pins=1)
        model.step(raw_pins=1)
        rising = model.step(raw_pins=1)

        model.step(raw_pins=0)
        model.step(raw_pins=0)
        falling = model.step(raw_pins=0)

        self.assertEqual(rising.rising_pins, 1)
        self.assertEqual(falling.falling_pins, 1)
        self.assertTrue(falling.events & Event.FALL)

    def test_wait_expires_after_full_subsequent_cycles(self):
        model = MachineModel(
            [
                Transition(
                    state=0,
                    require_events=Event.EXTERNAL,
                    next_state=1,
                    action=Action(wait_cycles=2),
                    name="start_wait",
                ),
                Transition(
                    state=1,
                    require_events=Event.TIMEOUT,
                    next_state=2,
                    name="timeout",
                ),
            ],
            state_count=3,
        )

        start = model.step(external_events=Event.EXTERNAL)
        middle = model.step()
        finish = model.step()

        self.assertEqual(start.state_after, 1)
        self.assertEqual(start.wait_remaining, 2)
        self.assertEqual(middle.wait_remaining, 1)
        self.assertFalse(middle.events & Event.TIMEOUT)
        self.assertTrue(finish.events & Event.TIMEOUT)
        self.assertEqual(finish.state_after, 2)
        self.assertEqual(finish.selected_transition, "timeout")

    def test_first_matching_transition_wins(self):
        model = MachineModel(
            [
                Transition(
                    state=0,
                    require_events=Event.EXTERNAL,
                    next_state=1,
                    name="first",
                ),
                Transition(
                    state=0,
                    require_events=Event.RX_READY,
                    next_state=2,
                    name="second",
                ),
            ],
            state_count=3,
        )

        result = model.step(
            external_events=Event.EXTERNAL | Event.RX_READY
        )

        self.assertEqual(result.selected_transition, "first")
        self.assertEqual(result.state_after, 1)

    def test_open_drain_low_and_release(self):
        model = MachineModel(
            [
                Transition(
                    state=0,
                    require_events=Event.EXTERNAL,
                    next_state=1,
                    action=Action(
                        data_mask=1,
                        data_value=0,
                        oe_mask=1,
                        oe_value=1,
                    ),
                    name="drive_low",
                ),
                Transition(
                    state=1,
                    require_events=Event.EXTERNAL,
                    next_state=2,
                    action=Action(oe_mask=1, oe_value=0),
                    name="release",
                ),
            ],
            state_count=3,
            open_drain_mask=1,
        )

        low = model.step(external_events=Event.EXTERNAL)
        released = model.step(external_events=Event.EXTERNAL)

        self.assertEqual(low.pin_data & 1, 0)
        self.assertEqual(low.output_enable & 1, 1)
        self.assertEqual(released.output_enable & 1, 0)
        self.assertIsNone(released.fault)

    def test_open_drain_drive_high_latches_safe_fault(self):
        model = MachineModel(
            [
                Transition(
                    state=0,
                    require_events=Event.EXTERNAL,
                    next_state=1,
                    action=Action(
                        data_mask=1,
                        data_value=1,
                        oe_mask=1,
                        oe_value=1,
                    ),
                    name="illegal_drive_high",
                )
            ],
            state_count=2,
            open_drain_mask=1,
        )

        result = model.step(external_events=Event.EXTERNAL)

        self.assertEqual(result.fault, "OPEN_DRAIN_DRIVE_HIGH")
        self.assertEqual(result.output_enable, 0)
        self.assertEqual(result.state_after, 0)

        later = model.step(external_events=Event.EXTERNAL)
        self.assertEqual(later.output_enable, 0)
        self.assertEqual(later.state_after, 0)
        self.assertEqual(later.fault, "OPEN_DRAIN_DRIVE_HIGH")

    def test_reset_clears_fault_and_releases_pins(self):
        model = MachineModel(
            [
                Transition(
                    state=0,
                    require_events=Event.EXTERNAL,
                    action=Action(
                        data_mask=1,
                        data_value=1,
                        oe_mask=1,
                        oe_value=1,
                    ),
                )
            ],
            state_count=1,
            open_drain_mask=1,
        )

        model.step(external_events=Event.EXTERNAL)
        self.assertIsNotNone(model.fault)

        result = model.step(raw_pins=255, rst_n=False)

        self.assertIsNone(result.fault)
        self.assertEqual(result.pin_data, 0)
        self.assertEqual(result.output_enable, 0)
        self.assertEqual(result.wait_remaining, 0)

    def test_input_guard(self):
        model = MachineModel(
            [
                Transition(
                    state=0,
                    input_mask=3,
                    input_value=2,
                    next_state=1,
                    name="match_input",
                )
            ],
            state_count=2,
        )

        model.step(raw_pins=2)
        model.step(raw_pins=2)
        result = model.step(raw_pins=2)

        self.assertEqual(result.sampled_pins, 2)
        self.assertEqual(result.state_after, 1)
        self.assertEqual(result.selected_transition, "match_input")

    def test_zero_wait_cancels_existing_wait(self):
        model = MachineModel(
            [
                Transition(
                    state=0,
                    require_events=Event.EXTERNAL,
                    action=Action(wait_cycles=5),
                    name="start",
                ),
                Transition(
                    state=0,
                    require_events=Event.RX_READY,
                    action=Action(wait_cycles=0),
                    name="cancel",
                ),
            ],
            state_count=1,
        )

        model.step(external_events=Event.EXTERNAL)
        result = model.step(external_events=Event.RX_READY)

        self.assertEqual(result.selected_transition, "cancel")
        self.assertEqual(result.wait_remaining, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
