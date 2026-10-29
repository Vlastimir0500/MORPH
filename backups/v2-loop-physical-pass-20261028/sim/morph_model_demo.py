from morph_model import Action, Event, MachineModel, Transition


def main():
    transitions = [
        Transition(
            state=0,
            require_events=Event.RISE,
            rise_mask=0b00000001,
            next_state=1,
            action=Action(
                data_mask=0b00000010,
                data_value=0,
                oe_mask=0b00000010,
                oe_value=0b00000010,
                wait_cycles=3,
            ),
            name="edge_drive_low",
        ),
        Transition(
            state=1,
            require_events=Event.TIMEOUT,
            next_state=0,
            action=Action(
                oe_mask=0b00000010,
                oe_value=0,
                wait_cycles=0,
            ),
            name="timeout_release",
        ),
    ]

    model = MachineModel(
        transitions=transitions,
        state_count=2,
        reset_state=0,
        open_drain_mask=0b00000010,
    )

    raw_sequence = [0, 1, 1, 1, 1, 1, 1, 1, 1, 1]
    snapshots = []

    print("cycle raw sampled rise events state data oe wait transition")

    for raw in raw_sequence:
        snapshot = model.step(raw_pins=raw)
        snapshots.append(snapshot)

        print(
            f"{snapshot.cycle:5} "
            f"{raw:3} "
            f"{snapshot.sampled_pins:7} "
            f"{snapshot.rising_pins:4} "
            f"{int(snapshot.events):6} "
            f"{snapshot.state_after:5} "
            f"{snapshot.pin_data:4} "
            f"{snapshot.output_enable:2} "
            f"{snapshot.wait_remaining:4} "
            f"{snapshot.selected_transition or '-'}"
        )

    start = next(
        s for s in snapshots
        if s.selected_transition == "edge_drive_low"
    )

    finish = next(
        s for s in snapshots
        if s.selected_transition == "timeout_release"
    )

    assert start.cycle == 4
    assert start.state_after == 1
    assert start.output_enable & 0b10
    assert start.wait_remaining == 3

    assert finish.cycle == 7
    assert finish.events & Event.TIMEOUT
    assert finish.state_after == 0
    assert not (finish.output_enable & 0b10)
    assert finish.fault is None

    print()
    print("PASS: MORPH edge-to-timed-release workload")
    print(f"Input event visible at cycle: {start.cycle}")
    print(f"Output released at cycle: {finish.cycle}")
    print(f"Event-to-release latency: {finish.cycle - start.cycle} cycles")


if __name__ == "__main__":
    main()
