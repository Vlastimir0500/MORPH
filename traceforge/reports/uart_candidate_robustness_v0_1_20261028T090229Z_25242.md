# TRACEFORGE â€” UART Candidate Robustness v0.1

- Validation gate: **PASS**
- Total cases: 1170
- RTL/reference-model mismatches: 0
- Production sources unchanged: True
- Promotion recommendation: **HOLD FOR REVIEW**

## Uniform-period matrix

- Cases: 568
- Counts: `{"correct_decode": 425, "error_flagged": 44, "silent_misdecode": 99}`
- Measured common envelope: 412â€“459 cycles; 384 cases; all correct: True
- Outside common envelope: 184 cases; counts `{"correct_decode": 41, "error_flagged": 44, "silent_misdecode": 99}`

| Payload | Correct period ranges (cycles) | Counts |
|---|---|---|
| 0x00 | 412â€“459 | `{"correct_decode": 48, "error_flagged": 11, "silent_misdecode": 12}` |
| 0xFF | 400â€“470 | `{"correct_decode": 71}` |
| 0x55 | 412â€“459 | `{"correct_decode": 48, "error_flagged": 11, "silent_misdecode": 12}` |
| 0x3C | 412â€“459 | `{"correct_decode": 48, "error_flagged": 11, "silent_misdecode": 12}` |
| 0x81 | 409â€“462 | `{"correct_decode": 54, "silent_misdecode": 17}` |
| 0x7E | 412â€“459 | `{"correct_decode": 48, "error_flagged": 11, "silent_misdecode": 12}` |
| 0xA5 | 409â€“462 | `{"correct_decode": 54, "silent_misdecode": 17}` |
| 0xA6 | 409â€“462 | `{"correct_decode": 54, "silent_misdecode": 17}` |

## Randomized symbol jitter

- Cases: 600; deterministic seed: 20261028

| Jitter amplitude (Â± cycles per symbol) | Cases | Correct | Silent misdecode | Error flagged | Core fault | RTL/model mismatches |
|---:|---:|---:|---:|---:|---:|---:|
| Â±20 | 150 | 150 | 0 | 0 | 0 | 0 |
| Â±40 | 150 | 150 | 0 | 0 | 0 | 0 |
| Â±60 | 150 | 145 | 4 | 1 | 0 | 0 |
| Â±80 | 150 | 138 | 7 | 5 | 0 | 0 |

## Malformed-frame controls

- Classification counts: `{"malformed_rejected": 2}`
- Both rejected as expected: True

## Decision

HOLD_FOR_REVIEW: this experiment is isolated candidate evidence; review timing-envelope and jitter failures, run the full release gate, and do not promote firmware automatically.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`
Production firmware SHA-256: `5a61cb59f5ccfabe6c10e92fc70b94a8bf3da34a136b76e1cc6e07adecb2ac5a`
