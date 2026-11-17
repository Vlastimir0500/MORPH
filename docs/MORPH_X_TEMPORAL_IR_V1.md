# MORPH X Temporal IR v1 — validated single-pin replay

This is **milestone 2a**, a deliberately limited, fail-closed compiler from an
existing MORPH X captured event buffer to executable V2 firmware. It integrates
the capture decoder, typed temporal IR, production assembler/disassembler and
independent cycle-accurate V2 reference model. It **does not add or change RTL**.

## Pipeline

```
8-event digital capture -> strict decoder -> single-pin event selection
   -> typed Temporal IR -> exact-cycle scheduler -> V2 assembler
   -> independent V2 model timing check -> .morph + .hex + JSON evidence
```

Example input: `examples/morph_x_replay_capture.json`

Run from repository root:

```bash
python compiler/morph_x_replay.py examples/morph_x_replay_capture.json --pin 0 \
  --output-dir build/morph-x-replay
python -m pytest -q sim/test_morph_x_replay.py
```

Emitted files: `replay.ir.json`, `replay.morph`, `replay.hex`,
`replay.report.json`. The hex words can be programmed through the existing
V2 loader interface. Real hardware operation needs a verified host transport.

## Typed representation

```json
{
  "schema": "morph-x.temporal-ir.v1",
  "clock_hz": 50000000,
  "pin": 0,
  "events": [{"cycle": 0, "value": 1}, {"cycle": 6, "value": 0}]
}
```

All timestamps are in clock cycles **relative to the first observed selected
pin transition**. Only single-pin, push-pull output transitions are supported.
Unrecognized fields or unsupported clock rates are rejected.

## Timing derivation

The unchanged V2 state machine alternates `FETCH` and `EXEC`. Consecutive
`DRIVE` instructions execute 2 cycles apart. An inserted `WAIT 0` adds 2
cycles; `WAIT n` with n>=1 adds `2+n` cycles. Consequently, exact gaps of
1 or 3 cycles are not representable. Other gaps >=2 are decomposed using
valid 0..255 WAIT instructions. The 64-word limit is enforced.

The compiler never silently rounds up or down an impossible interval; it fails
with a diagnostic. A generated program always releases its pin and halts after
the last reproduced event. The output-enable transition on release is **not**
part of the requested captured waveform.

## Evidence and limitations

- The V2 reference model is run from reset through release and halt.
  Every `DRIVE` event is checked at exact relative cycle offsets.
- The assembler/disassembler encoding round trip is verified.
- A deliberately mutated WAIT encoding must be rejected by the timing checker.
- Overflowed capture traces are rejected; timestamps are 16-bit modulo values.
  More than one full counter wrap between adjacent captures is ambiguous.
- Capture observes synchronized **input** pins, not necessarily the physical
  pads driven by the replay firmware; external electrical behavior, voltage,
  slew, analog quality and real asynchronous timestamps are not modeled.
- This is **model-validated firmware generation**, not a formal proof of
  compiler correctness and not yet an independent RTL differential replay test.
  It must still pass RTL/Cocotb validation for the generated program.
- Exactly one pin is replayed per program. Simultaneous multi-pin transitions,
  timed bidirectional turnarounds, triggered capture, and lossless streaming are
  not implemented here. They require explicit architectural changes.
- No on-silicon autonomous protocol inference, replay FIFO or replay engine is
  claimed; replay occurs by loading generated V2 firmware.
- The verified capture hardware and existing physical design remain unchanged.

## Next milestone (M2b)

Integrate the compiled replay program into the Cocotb and Verilator
RTL differential harness. Compare waveform transitions cycle by cycle; add
negative controls for wrong values, wrong timing and concurrency. Then freeze
and CI-qualify compiler artifacts before additional silicon features.
