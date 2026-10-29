# TRACEFORGE â€” UART Sample-Phase Margin Sweep v0.1

- Status: **PASS**
- Total simulated cases: 1704
- RTL/reference-model mismatches: 0
- Production RTL and firmware unchanged: True

## Candidate results

| Phase shift (cycles) | Wait value per instruction | Correct | Silent misdecode | Error flagged | Core fault | RTL/model mismatch | Common correct period range |
|---:|---:|---:|---:|---:|---:|---:|---|
| -8 | 211 | 425 | 99 | 44 | 0 | 0 | 412â€“459 |
| +0 | 215 | 425 | 103 | 40 | 0 | 0 | 413â€“460 |
| +8 | 219 | 429 | 103 | 36 | 0 | 0 | 413â€“461 |

## Per-payload measured ranges

### Phase shift -8 cycles

- 0x00: 412â€“459 cycles
- 0xFF: 400â€“470 cycles
- 0x55: 412â€“459 cycles
- 0x3C: 412â€“459 cycles
- 0x81: 409â€“462 cycles
- 0x7E: 412â€“459 cycles
- 0xA5: 409â€“462 cycles
- 0xA6: 409â€“462 cycles

### Phase shift +0 cycles

- 0x00: 413â€“460 cycles
- 0xFF: 400â€“470 cycles
- 0x55: 413â€“460 cycles
- 0x3C: 413â€“460 cycles
- 0x81: 410â€“463 cycles
- 0x7E: 413â€“460 cycles
- 0xA5: 410â€“463 cycles
- 0xA6: 410â€“463 cycles

### Phase shift +8 cycles

- 0x00: 413â€“461 cycles
- 0xFF: 400â€“470 cycles
- 0x55: 413â€“461 cycles
- 0x3C: 413â€“461 cycles
- 0x81: 411â€“464 cycles
- 0x7E: 413â€“461 cycles
- 0xA5: 411â€“464 cycles
- 0xA6: 411â€“464 cycles

## Interpretation

Use the measured common ranges to determine whether retiming improves tolerance or merely shifts the trade-off. Any candidate is experimental firmware only; no production source was modified.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`
Production firmware SHA-256: `5a61cb59f5ccfabe6c10e92fc70b94a8bf3da34a136b76e1cc6e07adecb2ac5a`
