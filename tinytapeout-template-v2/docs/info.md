# MORPH V2 — Modular Open Reprogrammable Protocol Hardware

## How it works

MORPH is a programmable **digital temporal protocol engine**. Rather than
hard-coding a different controller for every bus, a 16-bit instruction stream
controls eight bidirectional data pins, cycle waits, input sampling, serial
shifting, bounded edge waits, branches and a single counted loop. The 64-word
program is loaded after selecting the design; protocol behavior can be changed
by replacing the program without modifying the fabricated logic.

The clock target in `info.yaml` is 50 MHz (20 ns per cycle); it is a design
constraint, **not** a claim of silicon-measured performance. The programming
interface and protocol pins share the eight `uio` connections. Firmware examples
are in the repository's `protocols/` directory; the canonical V2 ISA and
reserved-bit policy are in `docs/isa_v2.md` at the repository root.

### Interface and startup

| Pins | Purpose |
| --- | --- |
| `clk` | Clock for the engine and program writes |
| `rst_n` | Active-low reset of execution state; program RAM is not cleared |
| `ena` | Gates the Tiny Tapeout bidirectional output enables |
| `ui_in[7]` | Program mode (`1` = write firmware / reset execution) |
| `ui_in[6]` | Program-word byte select (`0` = low, `1` = high) |
| `ui_in[5:0]` | Program address, 0–63 |
| `uio_in[7:0]` | Program data in write mode; digital protocol inputs in run mode |
| `uio_out[7:0]` | Protocol output-data bus |
| `uio_oe[7:0]` | Protocol output-enable bus (gated by `ena`, `rst_n` and program mode) |
| `uo_out[7:0]` | Current eight-bit shift register |

To load a 16-bit word at address `A`, set `rst_n=1`, `ui_in[7]=1`,
`ui_in[5:0]=A`, `ui_in[6]=0`, put its low byte on `uio_in` and apply a rising
clock edge. Then set `ui_in[6]=1`, put the high byte on `uio_in` and clock it.
Repeat for each required address. Set `ui_in[7]=0` to enter run mode. The
execution state is reset while program mode is asserted. Reset can be asserted
before running; allow the two-stage pin synchronizer to establish the initial
input value. The underlying memory is flip-flop-based and **not guaranteed to
contain any particular instruction after power-up**: load the program before
running each time the tile is powered up or reselected.

The external protocol inputs pass through two sequential synchronizer flip-flops
before the V2 `SAMPLE` and edge-detection logic uses them. This is a digital
synchronizer model, **not** a characterized metastability/MTBF guarantee.

### Instruction set

The implemented V2 opcodes are `HALT`, `DRIVE`, `SAMPLE`, `WAIT`, `EDGE`,
`SHIFT`, `BRANCH`, `RELEASE`, `BRANCH_SAMPLE`, `LOOP`, `LOAD_IMM`, `OD_SHIFT`,
and `DRIVE_SHIFT`. Canonical reserved bits must be zero; invalid encodings,
unsupported opcodes and bounded-edge timeouts enter a fault state and disable
protocol outputs. A valid `HALT` preserves the existing driven outputs: use
`RELEASE` when the firmware must tri-state a pin before halting.

Current programmable demonstrations include UART transmit/receive, SPI mode 0–3
programs, and I2C write/address-probe programs. Protocol support and timing
assertions are limited to the included executable models/tests, not universal
protocol compliance. The restricted typed temporal-contract compiler covers
only the documented V2 contract slice.

## How to test

1. Install Verilator, Icarus Verilog, Yosys, Python with pytest, Cocotb and make.
2. In the repository root run `python -m pytest -q sim` for model, ISA, and
   RTL-differential tests using Verilator.
3. Run `python compiler/morph_contract_v2.py
   protocols/v2_edge_timed_release.contract.json -o
   build/v2_edge_timed_release.contract-report.json -a
   build/v2_edge_timed_release.generated.morph` from a shell as **one line**.
   The output JSON must report `PASS`.
4. In `tinytapeout-template-v2/test`, run `make clean && make` and inspect
   `results.xml`. The testbench covers the Tiny Tapeout wrapper and representative
   programmed UART/SPI/I2C behavior.
5. The root GitHub Actions workflow generates GDS using the official
   `TinyTapeout/tt-gds-action@ttihp27a`, then runs Tiny Tapeout precheck,
   gate-level simulation, and a separate more stringent post-route physical
   signoff gate. All must be checked on the **same commit**. A mere completed
   GDS build is not evidence of electrical/timing signoff.

Verification details: `README.txt`, `docs/isa_v2.md`,
`docs/temporal_contract_v2.md`, and the Python/Cocotb tests in this repository.
The full V2 differential model is not a formal proof or silicon validation.

## External hardware

No additional hardware is required for software simulation. Real board testing
requires a clock, reset and a host that drives the documented firmware-loading
interface. Any physical open-drain I2C bus requires suitable external pull-ups;
other voltage levels require level shifting/transceivers and correct 3.3 V
digital-I/O handling on the Tiny Tapeout demo board. External electrical
requirements have not yet been characterized in silicon.

## Verification and disclosure notes

This design is an experimental open-source ASIC competition entry. Verification
uses hand-written and Python-generated tests, reference-model differential
checks, contract compilation, synthesis, gate-level testing and the Tiny Tapeout
physical flow. AI-assisted coding/review should be disclosed accurately in the
competition submission. Fabrication and lab measurement have **not** occurred.
