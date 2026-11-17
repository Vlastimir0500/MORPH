# MORPH X milestone 1: Timestamped capture / readback

**Status:** unqualified engineering prototype. No new physical-signoff claim.

## Baseline and hardware boundary

This branch is derived from the verified MORPH V2 release. V2's core RTL,
firmware and physical configuration are deliberately unchanged. An additional
capture module observes the synchronized digital *uio_in* signals. It does not
attempt to infer analog pad levels, metastability, precise asynchronous-edge
time, or wire-speed streaming.

The new capture unit has 8 × 32-bit event records. Each contains:

- `bits[31:16]`: 16-bit elapsed capture-clock timestamp, wrapping at 65536;
- `bits[15:8]`: mask of input pins whose synchronized values changed;
- `bits[7:0]`: current synchronized input levels.

It detects any change to the eight external digital inputs, recording one
snapshot for simultaneous transitions. Capture is enabled while the chip is
active, outside programming and read modes. Programming or reset clears the
record count and overflow flag. The input synchronizer is continuously
clocked; a one-cycle re-arming interval prevents a false event at startup.

The counter increments during active sampling. Readback *pauses* the capture
counter and recording. Changes during a read are intentionally omitted. No
claim of lossless or continuous capture is made.

## Host access and protocol compatibility

The original V2 program loading and pin output controls are unchanged:
`ui_in[7]` remains programming mode and `ui_in[6]` the programming high-byte
selector **when programming mode is asserted**.

When `ui_in[7]=0` and `ui_in[6]=0`, `uo_out` remains the original shift-register
output. When `ui_in[7]=0` and `ui_in[6]=1`, `uo_out` becomes a **read-only**
trace readback port. This mode does not write instruction RAM or alter any
`uio_out/uio_oe` protocol pin outputs.

With trace readback enabled:

- `ui_in[5]=1` returns the 8-bit trace **status**, ignoring the lower bits;
- `ui_in[5]=0` returns record byte selected by `ui_in[4:3]` and record index
  selected by `ui_in[2:0]`.
- Page 0: levels; page 1: changed-mask; page 2: timestamp low; page 3:
  timestamp high.
- Status bit `3:0` = event count (`0..8`), bit 4 = overflow, bit 5 = full,
  bit 6 = sampling primed, bit 7 = zero.
- Reading a record index >= count returns zero.

Capture and readback **share a mode** with normal shift-output observation;
firmware should rely on uio pins for its protocol physical signals. The host
must exit readback mode for continuous capture. In real TinyTapeout operation
`ena` may not be an externally controllable user signal; the design does not
require toggling it.

### Python readback command generation

```python
from morph_x_trace import read_command, decode_capture
ui_value_for_status = read_command(status=True)   # 0x60
ui_value_for_byte = read_command(slot=0, page=2) # 0x50
```

For each captured slot, collect pages 0/1/2/3 as `[levels, changed, t_lo,
t_hi]`. Export a JSON object `{"status": 66, "slots": [[1,1,7,0],
[3,2,10,0]]}` and use:

```bash
python compiler/morph_x_trace.py capture.json --vcd capture.vcd
```

The VCD waveform can be inspected in GTKWave or another compatible viewer.

## Validation matrix / explicit limits

- Run `python -m pytest -q sim` (adds decoder tests).
- Run Cocotb: original 22 V2 tests plus two capture tests (24 total).
- Run Yosys/OSS CAD formal qualifications with the new module included in
  the gating wrapper elaboration.
- Run all six physical/TinyTapeout engineering jobs again on the new commit.
- Review synthesis utilization and maximum clock frequency; the added trace
  registers may increase area and timing load. Fix all new failures before
  describing the design as physically passing.
- This module deliberately does not implement protocol inference, replay,
  fault injection, streaming FIFO or event-to-firmware compiler yet. Those
  remain dependent milestones in the unified MORPH X roadmap.

## Next milestones in the same architecture

1. Host capture transport and trigger/mask controls, plus trace integrity tests.
2. Shared Temporal IR for existing DSL, decoder and replay compiler.
3. Replay scheduler verified cycle-by-cycle against model and RTL.
4. JTAG/SWD/PS2/1-Wire protocol demonstration and Protocol Zero experiment.
5. Controlled timing/fault injection, richer formal assertions, benchmarks.
6. Full physical closure, GDS release and competition evidence.
