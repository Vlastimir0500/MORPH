# TRACEFORGE v0.1

TRACEFORGE is an isolated protocol-trace validation prototype for MORPH.

The first milestone generates a deterministic UART frame and three corrupted
variants, validates start/data/stop samples and nominal frame length, and emits
JSON and Markdown reports containing the cases and compressed waveform runs.

Run from the repository root:

    ~/.venvs/morph-test/bin/python -m unittest discover -s traceforge -p 'test_*.py' -v
    ~/.venvs/morph-test/bin/python traceforge/traceforge_uart.py

This version validates traces against an independent contract. It does not
execute MORPH RTL, prove hardware behavior, infer timing from arbitrary captures,
or minimize counterexamples.
