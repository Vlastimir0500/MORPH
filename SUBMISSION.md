# MORPH X — Jane Street Protocol Emulator ASIC Competition

- **Project:** Modular Open Reprogrammable Protocol Hardware (MORPH X)
- **Source:** [MORPH X public GitHub repository](https://github.com/Vlastimir0500/MORPH)
- **Target:** IHP SG13CMOS5L / Tiny Tapeout **8×4** allocation
- **Deadline:** January 18, 2027
- **Status:** engineering-qualified in earlier exact-commit CI runs; verify all jobs on this release's **own commit** before submission. Silicon has **not** been fabricated.

## For judges: where to look first

| Question | Primary evidence |
| --- | --- |
| What is the machine? | [README](README.md), [ISA specification](docs/isa_v2.md), [RTL](rtl/morph_engine_v2.sv) |
| Can it be programmed after fabrication? | [Tiny Tapeout top](tinytapeout-template-v2/src/project.v), [assembler](compiler/morph_assembler_v2.py), [protocol examples](protocols/) |
| How does capture/replay work? | [Capture module](tinytapeout-template-v2/src/morph_x_trace_capture.sv), [capture limits](docs/MORPH_X_CAPTURE_V01.md), [Temporal IR](docs/MORPH_X_TEMPORAL_IR_V1.md), [multi-pin constraints](docs/MORPH_X_MULTIPIN_V05.md) |
| Which protocols are demonstrated? | [UART, SPI and I²C programs](protocols/), [Pulse Link self-test](examples/morph_x_pulse_link_challenge.json) |
| How is it verified? | [Python / RTL differential tests](sim/), [Tiny Tapeout Cocotb tests](tinytapeout-template-v2/test/), [formal safety proofs](formal/qualification/), [CI workflows](.github/workflows/) |
| Where is the physical flow? | [Tiny Tapeout project](tinytapeout-template-v2/), [engineering workflow](.github/workflows/morph-engineering.yml), [custom report gate](scripts/check_physical_signoff.py) |
| What are the limits? | [Qualified claims and limitations](docs/MORPH_X_M6_LIMITATIONS.md), [independent blind challenge checklist](docs/MORPH_X_PROTOCOL_ZERO_EVIDENCE_CHECKLIST.md) |
| What about AI tools and licensing? | [AI usage statement](docs/AI_ASSISTANCE_DISCLOSURE.md), [Apache-2.0 license](LICENSE), [third-party notices](THIRD_PARTY_NOTICES.md) |

## Demonstrated architecture

A host loads a **64-word × 16-bit** firmware image into a small single-issue hardware engine. Implemented instructions include pin drive, release, sample, shift, bounded wait, input-edge wait, conditional branch and counted loop. Eight digital input pins can be observed through a bounded **eight-event** capture buffer, decoded by host software and converted into a strict Temporal IR for supported exact-cycle replay.

Hardware is programmed after fabrication through the documented programming interface. The **compiler and trace interpretation run on a host**, not as on-chip protocol inference. The single-issue machine cannot drive two independent pins on the same clock cycle and cannot represent exact one- or three-cycle gaps; unsupported schedules are rejected rather than silently retimed.

## Reproducibility commands

From repository root with Python 3.11, Verilator, Icarus Verilog, Yosys and OSS CAD Suite where applicable:

```bash
python3 scripts/audit_submission.py
python3 scripts/morph_x_m6_release.py audit --strict
python3 -m pytest -q sim
cd tinytapeout-template-v2/test && make clean && make && cd ../..
bash formal/qualification/run.sh
```

The complete Tiny Tapeout GDS, gate-level simulation and precheck are executed by the committed GitHub workflows. **Check that their successful `head_sha` equals the release HEAD**; do not reuse a green badge or report from an older branch as proof of this commit.

## Evidence categories: do not conflate

1. **Prior qualified M6 baseline**: README references earlier exact-commit GitHub runs with Python, Cocotb, formal and physical-design evidence. Those validate their own commits.
2. **This release commit**: passing current GitHub engineering + formal workflows are required before declaring this specific release qualified.
3. **Independent blind protocol**: *not yet verified*. Seeded, synthetic and self-authored protocols are self-tests, not an independently chosen post-freeze demonstration.
4. **Manufactured silicon**: none claimed. CI GDS and precheck do not demonstrate operation on an actual chip.

## Official rules and submission

Jane Street requires a **public GitHub repository URL**, RTL, tests, passing Tiny Tapeout GDS/precheck, architecture and ISA documentation, toolchain, example programs and verification write-up. A demo video is optional. The final form will be linked from the [official competition page](https://blog.janestreet.com/protocol-emulator-asic-competition/) when published.
