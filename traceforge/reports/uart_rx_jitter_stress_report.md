# TRACEFORGE v0.6 — UART Jitter Stress

- Total RTL simulations: 600
- RTL/reference-model mismatches: 0

| Jitter amplitude | Cases | Correct decode | Error flagged | Silent misdecode | Core fault |
|---:|---:|---:|---:|---:|---:|
| ±20 | 150 | 150 | 0 | 0 | 0 |
| ±40 | 150 | 150 | 0 | 0 | 0 |
| ±60 | 150 | 141 | 3 | 6 | 0 |
| ±80 | 150 | 129 | 2 | 19 | 0 |

## First non-correct cases

| Amplitude | Payload | Trial | Seed | Classification | Offsets (cycles) |
|---:|---|---:|---:|---|---|
| ±60 | 0x00 | 8 | 26261036 | error_flagged | `[52, 49, 20, 40, 43, -55, 50, -9, 50, -37]` |
| ±60 | 0x00 | 17 | 26261045 | error_flagged | `[-9, 43, 53, 57, 5, 26, 57, -34, 54, 22]` |
| ±60 | 0x00 | 23 | 26261051 | silent_misdecode | `[-19, 5, -47, -57, 9, -36, -40, -59, 28, 28]` |
| ±60 | 0x55 | 21 | 26346049 | error_flagged | `[24, 18, 12, 54, 31, 19, 56, 18, 48, -25]` |
| ±60 | 0x81 | 24 | 26390052 | silent_misdecode | `[60, 56, 31, 41, -10, 30, 41, -14, 10, 3]` |
| ±60 | 0xA5 | 11 | 26426039 | silent_misdecode | `[-5, -59, -10, -18, -51, -49, -36, 3, -12, -39]` |
| ±60 | 0xA5 | 28 | 26426056 | silent_misdecode | `[55, 48, 49, 26, 55, 58, 37, 46, -38, -12]` |
| ±60 | 0xA6 | 7 | 26427035 | silent_misdecode | `[39, -8, 3, 53, -1, 57, 51, 36, -53, -52]` |
| ±60 | 0xA6 | 14 | 26427042 | silent_misdecode | `[47, -14, 42, 28, 13, 53, 58, 41, -8, -8]` |
| ±80 | 0x00 | 3 | 28261031 | silent_misdecode | `[-62, -57, 23, -24, -66, -34, -12, 32, -21, 50]` |
| ±80 | 0x00 | 16 | 28261044 | silent_misdecode | `[-13, -34, -76, -62, 65, -67, -51, -61, 29, 43]` |
| ±80 | 0x00 | 21 | 28261049 | silent_misdecode | `[-71, 11, -41, -7, -66, -62, -72, -58, -11, 22]` |
| ±80 | 0x00 | 23 | 28261051 | silent_misdecode | `[77, -79, -80, 54, -76, -80, -8, -34, 8, -2]` |
| ±80 | 0x00 | 27 | 28261055 | silent_misdecode | `[-61, -25, -49, 58, -48, -54, -80, -55, 36, 64]` |
| ±80 | 0x55 | 2 | 28346030 | silent_misdecode | `[56, 3, 50, 61, 50, -27, 59, -79, -67, 28]` |
| ±80 | 0x55 | 20 | 28346048 | error_flagged | `[55, 34, 66, 12, 80, 66, -57, 31, 38, 63]` |
| ±80 | 0x55 | 26 | 28346054 | error_flagged | `[31, 61, 18, -8, -62, 74, 73, 13, 68, -63]` |
| ±80 | 0x81 | 3 | 28390031 | silent_misdecode | `[-51, -73, -49, -51, -42, -43, -23, 3, -20, 5]` |
| ±80 | 0x81 | 24 | 28390052 | silent_misdecode | `[-78, -27, -37, -76, -14, 2, -61, 5, 74, -22]` |
| ±80 | 0x81 | 26 | 28390054 | silent_misdecode | `[71, 23, 58, 2, 40, 42, 47, -12, 19, -32]` |
| ±80 | 0x81 | 27 | 28390055 | silent_misdecode | `[-31, 37, -76, 29, -51, -62, -65, -22, -19, -66]` |
| ±80 | 0xA5 | 1 | 28426029 | silent_misdecode | `[73, 74, -24, 23, 39, 63, 36, -13, -22, -40]` |
| ±80 | 0xA5 | 10 | 28426038 | silent_misdecode | `[76, 58, 70, 12, -78, -67, 80, 74, -73, -73]` |
| ±80 | 0xA5 | 13 | 28426041 | silent_misdecode | `[-62, -70, 73, -69, -71, -16, -38, -54, 62, 6]` |
| ±80 | 0xA5 | 20 | 28426048 | silent_misdecode | `[34, -34, -23, -79, -63, -50, -76, -19, 57, -13]` |
| ±80 | 0xA5 | 21 | 28426049 | silent_misdecode | `[-26, -59, -9, -57, -62, -1, -39, 11, 72, 49]` |
| ±80 | 0xA5 | 24 | 28426052 | silent_misdecode | `[-30, -80, -38, 71, -75, -37, 3, -74, -75, 71]` |
| ±80 | 0xA6 | 1 | 28427029 | silent_misdecode | `[33, 60, 65, 72, 11, 56, -6, 13, -16, 38]` |
| ±80 | 0xA6 | 11 | 28427039 | silent_misdecode | `[3, 70, 31, 38, -25, 64, 16, 74, 53, -25]` |
| ±80 | 0xA6 | 27 | 28427055 | silent_misdecode | `[-12, -45, 25, -52, -37, -50, -79, -10, -67, 39]` |

Every case uses independent deterministic duration perturbations per symbol. Results are empirical for this UART receiver and the chosen seeds, not a universal tolerance guarantee.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`

