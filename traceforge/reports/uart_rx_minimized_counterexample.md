# TRACEFORGE v0.7 — Minimized UART Counterexample

- Source failure seed: `26261051`
- Payload: `0x00`
- Original offsets: `[-19, 5, -47, -57, 9, -36, -40, -59, 28, 28]`
- Minimized offsets: `[-9, 0, -15, -57, 0, -36, -40, -59, 0, 0]`
- Original absolute offset sum: 328
- Minimized absolute offset sum: 216
- Nonzero offsets: 10 → 6
- RTL/reference model match: True
- Observed shift register: 0x01
- Expected shift register: 0x00
- Error flag: False
- Core fault: False
- Final classification: `silent_misdecode`
- RTL simulation evaluations: 98
- Local reduction checks: PASS

This is a greedy, locally minimized counterexample, not a proof of global minimality.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`

Waveform vector file: `traceforge/reports/uart_rx_minimized_counterexample_vectors.hex`

