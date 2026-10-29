# TRACEFORGE UART Phase Sweep v0.1

- Execution gate: **PASS**
- Total simulations: 17760
- Production sources unchanged: True
- RTL/reference mismatches: zero = True

| Phase shift | WAIT value | Correct matrix | Silent matrix | Flagged matrix | Common correct period range | Jitter correct | Jitter silent | Counterexample |
|---:|---:|---:|---:|---:|---|---:|---:|---|
| -4 | 213 | 425 | 87 | 56 | [[409, 456]] | 578 | 13 | [{'classification': 'correct_decode', 'observed_shift': '0x00'}] |
| -4 | 213 | 425 | 95 | 48 | [[411, 458]] | 581 | 12 | [{'classification': 'correct_decode', 'observed_shift': '0x00'}] |
| -4 | 213 | 432 | 96 | 40 | [[412, 460]] | 581 | 13 | [{'classification': 'correct_decode', 'observed_shift': '0x00'}] |
| -4 | 213 | 425 | 107 | 36 | [[414, 461]] | 581 | 15 | [{'classification': 'silent_misdecode', 'observed_shift': '0x01'}] |
| -4 | 213 | 432 | 108 | 28 | [[415, 463]] | 582 | 16 | [{'classification': 'silent_misdecode', 'observed_shift': '0x01'}] |
| -2 | 214 | 425 | 87 | 56 | [[409, 456]] | 578 | 13 | [{'classification': 'correct_decode', 'observed_shift': '0x00'}] |
| -2 | 214 | 425 | 95 | 48 | [[411, 458]] | 582 | 12 | [{'classification': 'correct_decode', 'observed_shift': '0x00'}] |
| -2 | 214 | 432 | 96 | 40 | [[412, 460]] | 582 | 12 | [{'classification': 'correct_decode', 'observed_shift': '0x00'}] |
| -2 | 214 | 432 | 104 | 32 | [[414, 462]] | 582 | 14 | [{'classification': 'silent_misdecode', 'observed_shift': '0x01'}] |
| -2 | 214 | 432 | 108 | 28 | [[415, 463]] | 582 | 16 | [{'classification': 'silent_misdecode', 'observed_shift': '0x01'}] |
| +0 | 215 | 425 | 87 | 56 | [[409, 456]] | 578 | 13 | [{'classification': 'correct_decode', 'observed_shift': '0x00'}] |
| +0 | 215 | 425 | 95 | 48 | [[411, 458]] | 583 | 11 | [{'classification': 'correct_decode', 'observed_shift': '0x00'}] |
| +0 | 215 | 425 | 103 | 40 | [[413, 460]] | 582 | 12 | [{'classification': 'silent_misdecode', 'observed_shift': '0x01'}] |
| +0 | 215 | 432 | 104 | 32 | [[414, 462]] | 581 | 15 | [{'classification': 'silent_misdecode', 'observed_shift': '0x01'}] |
| +0 | 215 | 432 | 112 | 24 | [[416, 464]] | 582 | 16 | [{'classification': 'silent_misdecode', 'observed_shift': '0x01'}] |

## Paired deltas against baseline WAIT=215

| Phase shift | Correct delta | Silent misdecode delta | Flagged error delta | Improved cases | Regressed cases |
|---:|---:|---:|---:|---:|---:|
| -4 | +2 | -21 | +19 | 37 | 35 |
| -4 | +5 | -14 | +9 | 22 | 17 |
| -4 | +11 | -11 | +0 | 12 | 1 |
| -4 | -9 | +15 | -6 | 8 | 17 |
| -4 | -1 | +17 | -16 | 27 | 28 |
| -2 | +2 | -21 | +19 | 37 | 35 |
| -2 | +6 | -14 | +8 | 22 | 16 |
| -2 | +10 | -10 | +0 | 10 | 0 |
| -2 | -1 | +11 | -10 | 16 | 17 |
| -2 | -1 | +17 | -16 | 27 | 28 |
| +0 | +2 | -21 | +19 | 34 | 32 |
| +0 | +7 | -15 | +8 | 22 | 15 |
| +0 | -2 | +12 | -10 | 17 | 19 |
| +0 | -1 | +21 | -20 | 34 | 35 |

## Decision

HOLD_FOR_REVIEW: select no production firmware setting automatically; review common timing ranges, regressions, jitter results, and the existing release gate.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`
Production firmware SHA-256: `5a61cb59f5ccfabe6c10e92fc70b94a8bf3da34a136b76e1cc6e07adecb2ac5a`
