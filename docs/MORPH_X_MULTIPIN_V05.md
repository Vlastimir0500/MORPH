# MORPH X M4 — exact multi-pin Temporal IR (candidate)

## Design goal

Preserve hardware from verified `morph-x-e2e-v0.4`, and increase host compiler
coverage from one output pin to several independently timed pins. The compiler
reproduces *recorded digital drive levels after each scheduled transition* at
exact **relative** V2 clock-cycle offsets, or rejects schedules it cannot
represent. It does not infer physical voltage levels, analog timing or
whether a replayed master/slave protocol will be accepted by a target.

## IR schema

```json
{
  "schema": "morph-x.multi-pin-ir.v1",
  "clock_hz": 50000000,
  "pins": [0,1],
  "events": [
    {"cycle":0,"pin":0,"value":1},
    {"cycle":6,"pin":1,"value":1},
    {"cycle":12,"pin":0,"value":0}
  ]
}
```

Every pin must be listed exactly once, ascending. Events are chronologically
ordered globally; the first event is at cycle zero. The timestamps here are
*relative to the earliest selected transition*, not the capture counter epoch.

## Strict correctness constraints

- The V2 ISA is single-issue and only updates one selected pin per `DRIVE`.
  **Simultaneous selected-pin changes are rejected**. No one-cycle or
  three-cycle inter-DRIVE gaps; the compiler never moves edges silently.
- Unselected input transitions are filtered but their elapsed time contributes
  to selected transitions' relative schedule.
- Capture overflow, inconsistent changed masks, unsupported input types,
  duplicated pin levels, invalid pins, clock mismatch, and >64 program words
  cause explicit rejection.
- Captured event storage remains **eight records**, not streaming or DMA.
  A single 16-bit timestamp wrap between records is interpreted modulo 65536;
  multiple complete wraps are inherently undetectable from this record format.
- Output-enable transitions are not equal to physically observed input edges.
  First output activation has no guaranteed preceding physical level; repeated
  pin levels are rejected. All driven pins are explicitly released then HALT.
- Only push-pull digital outputs are modeled by this compiler. Open drain,
  simultaneous edges, dynamic bidirectional turnaround, accurate pre-drive
  initialization and asynchronous hardware acceptance need further work.

## Reproduction

```
input levels on 2 pins -> 8x32 trace register -> uo_out readback
 -> strict multi-pin IR -> V2 assembler -> V2 model exact-cycle checker
 -> program via byte loader -> top-level uio_out / uio_oe timing checks
 -> Verilator state-by-state RTL comparison
```

The included SPI-like demonstration is **two clock pulses with chip select and
MOSI choreography**. It is a pin-level scheduling example, **not** a full
SPI-mode conformance claim, slave-acknowledged transaction or a protocol
certification.

## Commands

```bash
python compiler/morph_x_multireplay.py examples/morph_x_multipin_capture.json --pins 0 1 --output-dir build/m4_capture
python compiler/morph_x_multireplay.py examples/morph_x_spi_two_bit_ir.json --output-dir build/m4_spi
```

Files: `multi.ir.json`, `multi.morph`, `multi.hex`, `multi.report.json`.
Each report identifies constraints, program/IR hashes, model cycles and exact
requested transitions. Full M4 qualification additionally requires Python,
Verilator, Cocotb, GitHub formal, TinyTapeout precheck, GDS, gate-level and
physical-signoff gates on **one matching Git commit**.

## Future hardware decision

Before adding atomic multi-pin writes to RTL, compare how many target protocol
schedules truly require simultaneous edges and characterize the silicon area,
timing and control-bit tradeoffs. Existing release tags must remain immutable.
