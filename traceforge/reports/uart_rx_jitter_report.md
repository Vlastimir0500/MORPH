# TRACEFORGE v0.5 — UART Jitter Experiment

- Total cases: 150
- Nominal symbol period: 436 cycles
- Per-symbol jitter: ±20 cycles
- Fixed, reproducible seeds: yes

| Payload | Correct | Error flagged | Silent misdecode | RTL/model mismatch |
|---|---:|---:|---:|---:|
| 0x00 | 30 | 0 | 0 | 0 |
| 0x55 | 30 | 0 | 0 | 0 |
| 0x81 | 30 | 0 | 0 | 0 |
| 0xA5 | 30 | 0 | 0 | 0 |
| 0xA6 | 30 | 0 | 0 | 0 |

The experiment uses synthetic independent timing offsets for the start, data and stop symbol durations. It is a deterministic stress experiment, not a claim about a universal UART timing specification.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`

