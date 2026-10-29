# TRACEFORGE v0.4 — UART Payload/Timing Matrix

- Payloads: 8
- Bit periods: 71
- Total RTL runs: 568
- Cycle-by-cycle RTL/model mismatches: 0

| Payload | Correct decode ranges (cycles) | Correct | Silent misdecode | Error flagged |
|---|---|---:|---:|---:|
| 0x00 | [[413, 460]] | 48 | 13 | 10 |
| 0xFF | [[400, 470]] | 71 | 0 | 0 |
| 0x55 | [[413, 460]] | 48 | 13 | 10 |
| 0x3C | [[413, 460]] | 48 | 13 | 10 |
| 0x81 | [[410, 463]] | 54 | 17 | 0 |
| 0x7E | [[413, 460]] | 48 | 13 | 10 |
| 0xA5 | [[410, 463]] | 54 | 17 | 0 |
| 0xA6 | [[410, 463]] | 54 | 17 | 0 |

## Interpretation

Correct-decode ranges are empirical for this receiver program, payload, clock model and trace generator. Timing results are not a general UART specification.
Silent misdecode means the final shifted byte differs from the expected byte without the receiver's pin-7 error flag or core fault being asserted.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`

