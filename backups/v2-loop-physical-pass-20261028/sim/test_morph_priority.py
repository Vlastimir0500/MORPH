import unittest

from morph_model import Action, Event, MachineModel, Transition


class PriorityTests(unittest.TestCase):
    def make_model(self, edge_first):
        starter = Transition(
            state=0,
            require_events=Event.EXTERNAL,
            action=Action(wait_cycles=3),
            name="start_wait",
        )

        edge = Transition(
            state=0,
            require_events=Event.RISE,
            rise_mask=1,
            next_state=1,
            name="edge",
        )

        timeout = Transition(
            state=0,
            require_events=Event.TIMEOUT,
            next_state=2,
            name="timeout",
        )

        order = [edge, timeout] if edge_first else [timeout, edge]

        return MachineModel(
            [starter, *order],
            state_count=3,
        )

    def run_to_simultaneous_events(self, model):
        model.step(external_events=Event.EXTERNAL)
        model.step(raw_pins=1)
        model.step(raw_pins=1)
        return model.step(raw_pins=1)

    def test_edge_wins_when_listed_first(self):
        model = self.make_model(edge_first=True)
        result = self.run_to_simultaneous_events(model)

        self.assertTrue(result.events & Event.RISE)
        self.assertTrue(result.events & Event.TIMEOUT)
        self.assertEqual(result.selected_transition, "edge")
        self.assertEqual(result.state_after, 1)

    def test_timeout_wins_when_listed_first(self):
        model = self.make_model(edge_first=False)
        result = self.run_to_simultaneous_events(model)

        self.assertTrue(result.events & Event.RISE)
        self.assertTrue(result.events & Event.TIMEOUT)
        self.assertEqual(result.selected_transition, "timeout")
        self.assertEqual(result.state_after, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
