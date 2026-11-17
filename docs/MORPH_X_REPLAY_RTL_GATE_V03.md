# MORPH X Replay-to-RTL regression gate V0.3

## Purpose

This adds **three** tests to the existing `pytest -q sim` suite. The tests:

1. Parse the committed example capture JSON into the typed Temporal IR.
2. Compile that IR into a 64-word-compatible MORPH V2 machine program.
3. Validate relative output-transition timing using the independent ISA model.
4. Use the existing Verilator differential testbench to compare *every sampled
   RTL cycle* against that model, including output enables and fault state.
5. Repeat for pins 3 and 7 with distinct timing schedules.

Verilator must be available; this test does not quietly skip the RTL requirement.

## Critical limits

This is **not** a live hardware capture -> replay end-to-end test. The fixture
is a captured-data-format JSON example, not a claim of silicon capture.
The test exercises the V2 protocol engine RTL, not an end-to-end TinyTapeout
host readback / programming controller. Capture RTL already has its own two
Cocotb tests. Combining those stages at top level is a future milestone.

No physical-design files, ISA semantics, source RTL, firmware, SDC, or
verification harness internals are modified by this package.

## Reproduction

From `~/MORPH-X` with OSS-CAD/Verilator and the Python test venv accessible:

```sh
cd ~/MORPH-X
export PATH="$HOME/.venvs/morph-test/bin:/usr/local/bin:/usr/bin:/bin:$HOME/tools/oss-cad-suite/bin"
python -m pytest -q sim/test_morph_x_replay_rtl.py -v
python -m pytest -q sim
```

Expected outcome: the previous 184 tests plus these three = **187 tests**, if
all prior tests still pass. Exact count may vary if other tests have changed.

The CI `rtl-regression` job already runs `python -m pytest -q sim` after
installing Verilator, so this file is an enforced GitHub check once committed.
