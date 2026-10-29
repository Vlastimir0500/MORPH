MORPH — Modular Open Reprogrammable Protocol Hardware

MORPH is a post-fabrication-programmable digital protocol engine for the Jane Street Protocol Emulator ASIC Competition. The V2 RTL executes a compact instruction stream that controls protocol pins and timing rather than relying solely on fixed-function UART/SPI/I2C blocks.

V2 hardware overview
- 8-bit protocol input, output and output-enable buses
- 64-word x 16-bit program memory
- Pin drive and release, input sampling, shift register, cycle wait, bounded edge wait, branch, sample-conditioned branch, counted loop, halt and fail-safe fault paths
- Example protocol programs and TinyTapeout Cocotb tests are in the repository

Key entry points
- `rtl/morph_engine_v2.sv`: production V2 RTL
- `tinytapeout-template-v2/src/morph_engine.sv`: TinyTapeout mirror of the production engine
- `compiler/morph_assembler_v2.py`: assembler/disassembler for the V2 ISA
- `sim/morph_isa_model_v2.py`: V2 executable reference model
- `sim/test_morph_rtl_diff_v2.py`: cycle-by-cycle model-versus-RTL differential tests using Verilator
- `protocols/`: example UART, SPI and I2C programs
- `compiler/morph_contract.py`: earlier V1 contract-validation prototype; it is not the V2 checker
- `compiler/morph_contract_v2.py`: restricted V2 typed temporal-contract compiler and scenario checker
- `docs/temporal_contract_v2.md`: scope, semantics, assumptions and evidence boundaries for the V2 contract slice

Run the local verification suite from the repository root

```bash
mkdir -p build
python -m pytest -q sim
python compiler/morph_contract_v2.py protocols/v2_edge_timed_release.contract.json -o build/v2_edge_timed_release.contract-report.json -a build/v2_edge_timed_release.generated.morph
```

The pytest suite requires Verilator for the cycle-by-cycle RTL differential harness. The contract command emits generated assembly, machine words, hashes, explicit timing checks and a JSON report. The restricted contract language deliberately rejects unsupported operations; it is not a general protocol-specification compiler.

Engineering evidence and limits

The GitHub Actions workflow checks protected source hashes and the TinyTapeout mirror, runs Python/RTL tests, performs Yosys synthesis and runs the TinyTapeout physical flow. A passing model simulation is not a formal proof. GDS generation is not equivalent to full DRC/LVS/STA signoff, and generic Yosys statistics are not technology-mapped area or timing. The V2 temporal-contract path must pass its actual RTL differential test before claims of contract-to-RTL conformance are made. Gate-level and physical acceptance remain separate evidence gates.

Research direction

MORPH's differentiator is intended to be a restricted temporal contract that compiles to executable V2 instructions and produces reproducible conformance evidence: an independent model, expected-versus-observed timing events, adversarial traces and selected formal safety properties. The first implementation demonstrates only a bounded edge/release slice. It does not yet establish arbitrary compiler correctness, general protocol conformance or complete hardware signoff.
