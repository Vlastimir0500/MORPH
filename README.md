# MORPH V2 — programmable temporal protocol fabric

**Jane Street Protocol Emulator ASIC Competition · March 2027 CMOS5L target · Tiny Tapeout 8×4**

MORPH is a post-fabrication-programmable protocol engine that executes an
instruction sequence governing eight digital protocol pins. It aims to make
**timing and pin sequencing a software-defined resource**, rather than building
a separate fixed-function UART, SPI and I²C peripheral for every task.

The hardware and compiler are experimental. A passing simulation, GDS file or
precheck is **not** proof of silicon behavior; actual evidence is tracked per
GitHub Actions commit, with separate physical checks.

## Architecture at a glance

- **Engine:** `rtl/morph_engine_v2.sv`, mirrored byte-for-byte into the Tiny
  Tapeout project's `src/morph_engine.sv`.
- **Program store:** 64 × 16-bit writable instruction memory; host loads a low
  and high byte at each address using the `ui_in` programming controls and
  `uio_in` data bus.
- **Datapath:** eight tri-state-capable bidirectional pins, 8-bit shift
  register, sample bit, a bounded edge-wait counter, branching and one
  counted loop.
- **Clocking:** nominal 50 MHz target (20 ns period). Protocol inputs enter a
  two-stage digital synchronizer before SAMPLE/EDGE handling; no analog MTBF
  characterization is claimed.
- **Safe fault behavior:** invalid instruction encodings and bounded EDGE
  timeouts disable protocol output enables; a normal HALT preserves the
  current output state unless firmware explicitly RELEASEs pins.
- **Fabrication target:** IHP 130 nm CMOS5L, 8×4 Tiny Tapeout tiles, standard
  Tiny Tapeout GDS and precheck flow.

## Demonstrated firmware and tools

| Category | Programs / implementation | Verification path |
| --- | --- | --- |
| UART | `protocols/v2_uart_tx_a5.*`, `v2_uart_rx_a6.*` | Cocotb and model/RTL tests |
| SPI | `protocols/v2_spi_mode0_a5.*` through `v2_spi_mode3_a5.*` | Cocotb and model/RTL tests |
| I²C | `protocols/v2_i2c_write_*.{morph,hex}`, `v2_i2c_address_probe.*` | Cocotb and model/RTL tests |
| ISA/toolchain | `compiler/morph_assembler_v2.py` | Python regression + RTL differential |
| Typed contract (limited subset) | `compiler/morph_contract_v2.py` | Contract report and generated-program differential |

These are tested **examples**, not claims of standards certification, arbitrary
protocol operation, full electrical compliance, or production firmware readiness.

## Interface and ISA

The programming and pin mapping, power-up/reload requirements, and testing
procedure are documented in
[`tinytapeout-template-v2/docs/info.md`](tinytapeout-template-v2/docs/info.md).
The canonical 16-bit ISA, reserved-bit policy, and fault semantics are in
[`docs/isa_v2.md`](docs/isa_v2.md).
The typed temporal-contract research slice and its limitations are in
[`docs/temporal_contract_v2.md`](docs/temporal_contract_v2.md).

## Reproduce local verification

In a Linux/WSL environment with Python pytest, Verilator, Icarus, Cocotb,
Yosys and make installed:

```bash
python -m pytest -q sim
python compiler/morph_contract_v2.py protocols/v2_edge_timed_release.contract.json   -o build/v2_edge_timed_release.contract-report.json   -a build/v2_edge_timed_release.generated.morph
cd tinytapeout-template-v2/test && make clean && make
```

The root
[`.github/workflows/morph-engineering.yml`](.github/workflows/morph-engineering.yml)
runs the RTL regression, Cocotb, official Tiny Tapeout CMOS5L GDS hardening,
Tiny Tapeout precheck, gate-level simulation, and a **separate stringent
physical-signoff gate**. Check the results for the exact intended commit;
individual green jobs do not mean the entire workflow passed.

Physical-design custom constraints and post-GRT repair substitutions are in
`tinytapeout-template-v2/src/config.json` and the two `morph_*.sdc` files.
The final signoff checks are implemented in
`scripts/check_physical_signoff.py`. The source-level and physical-design
evidence have distinct limitations; see `README.txt` for the detailed project
background.

## Competition entry status and disclosure

The deadline is **January 18, 2027**. A public repository, source RTL, tests,
example firmware/toolchain, readable design/ISA/verification documentation, and
a **passing Tiny Tapeout GDS/precheck on the submitted commit** are required.
The separate MORPH max-fanout gate is an additional engineering criterion, not
an extra rule imposed by Jane Street. The owner must submit the repository
through Jane Street's published submission form once available; scripts do not
submit competition entries automatically.

AI-assisted work is part of the engineering workflow. Generated changes are
reviewed and validated with executable tests and physical reports, and the
competition submission should disclose AI assistance accurately. Fabrication
and actual silicon measurements have not taken place.
