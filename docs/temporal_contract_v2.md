# MORPH V2 temporal-contract conformance slice

## Purpose

This directory documents a restricted first implementation of the MORPH research thesis: take a typed temporal-operation contract, compile it to the existing V2 instruction set, check explicit timing expectations against the V2 Python reference model, and run the generated program and the same pin-input trace through the production RTL differential testbench.

This is translation validation for a deliberately small language subset. It is not a general protocol-specification compiler and it does not prove arbitrary protocol correctness.

## Evidence path

1. `protocols/v2_edge_timed_release.contract.json` is the declarative input. Its `program` field contains typed operations; each operation is validated for exact fields and legal ranges.
2. `compiler/morph_contract_v2.py` translates those operations to V2 assembly, assembles and disassembles the result with `compiler/morph_assembler_v2.py`, checks program and timeout limits, then evaluates the scenarios using `sim/morph_isa_model_v2.py`.
3. The checker writes a JSON report containing the contract hash, generated-source hash, machine-program hash, disassembly, assumptions, expected and observed transitions, and final state checks. The generated assembly can be written separately for inspection.
4. `sim/test_morph_rtl_diff_v2.py` loads the same generated machine words and scenario input trace into the existing Verilator differential harness. That harness compares the model's cycle-by-cycle state and pin outputs with the actual V2 RTL.
5. The deliberately mutated timing expectation and shorter edge timeout in `sim/test_morph_contract_v2.py` are negative controls: the checker must reject those changed expectations.
6. GitHub Actions runs the contract checker, runs the Python/RTL test suite, and uploads the contract report. The gate-level job copies TinyTapeout's existing test directory to a real root-level test directory because the action expects that path. The vendored test harness remains unchanged.

## Restricted operation set

Schema version 2 currently accepts typed `drive`, `wait_cycles`, `wait_edge`, `release`, `sample`, `shift`, and `halt` operations. A linear program must terminate with `halt`; `halt` may appear only at the end. Branching, loops, nested behavior, parallel execution and arbitrary temporal logic are outside this first contract subset. Unsupported operations and unknown fields are errors rather than silently approximated behavior.

For `wait_edge`, `timeout_cycles` in the range 1–127 generates a bounded `EDGE` instruction. A value of 0 generates the ISA's unbounded edge wait, but the contract checker rejects unbounded waits because they cannot satisfy a finite temporal bound. `wait_cycles` generates the existing V2 `WAIT` instruction. Timing is expressed in model clock cycles, with cycle 1 reserved for reset and the first scenario input sample applied in cycle 2.

## Demonstrated contract

The checked-in example drives pin 0 high, waits for a rising edge on pin 0 with a six-cycle timeout, releases pin 0 and halts.

- Success scenario: pin 0 output-enable becomes 1 at cycle 3 and returns to 0 at cycle 9; no fault or timeout should occur.
- Missing-edge scenario: output-enable becomes 1 at cycle 3 and returns to 0 at cycle 11; `fault` and `timed_out` assert at cycle 11, and the engine halts.

The expected assembly is saved as `protocols/v2_edge_timed_release.expected.morph`. The test suite requires the compiler to reproduce it exactly.

## Assumptions and limitations

- Pin inputs are represented as an 8-bit synchronous value sampled on rising clock edges.
- The reference model and RTL differential run cover digital behavior. They do not model analogue edge quality, metastability, external synchronizers, pull-up impedance, voltage levels or board-level electrical behavior.
- A passing Python scenario is model evidence only. The contract-to-RTL claim requires the Verilator differential test to pass for each generated scenario.
- The model/RTL comparison is not by itself a formal proof that the RTL is correct. Mutation controls increase confidence in this specific checker but do not establish completeness.
- Gate-level simulation and full physical signoff are separate gates. GDS generation, generic synthesis statistics or a passing precheck must not be represented as complete DRC/LVS/STA signoff.
- The V1 contract checker remains unchanged. This new checker is an independent V2 entry point so the legacy model is not silently presented as the V2 reference semantics.

## Commands

```bash
mkdir -p build
python compiler/morph_contract_v2.py protocols/v2_edge_timed_release.contract.json -o build/v2_edge_timed_release.contract-report.json -a build/v2_edge_timed_release.generated.morph
python -m pytest -q sim
```

The second command includes V2 model/RTL differential testing and the generated-contract scenarios when Verilator is installed. The full TinyTapeout RTL and gate-level flows are run separately by the GitHub Actions workflow.
