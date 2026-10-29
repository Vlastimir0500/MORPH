# TRACEFORGE â€” UART Candidate Validation v0.1

- Status: **PASS**
- Cases: 66
- RTL/reference-model mismatches: 0
- Production RTL/firmware unchanged: True

## Candidate summary

| Phase shift | Correct | Silent misdecode | Error flagged | Core fault | RTL/model mismatch | Minimized counterexample |
|---:|---:|---:|---:|---:|---:|---|
| -8 | 22 | 0 | 0 | 0 | 0 | correct_decode |
| +0 | 16 | 6 | 0 | 0 | 0 | silent_misdecode |
| +8 | 8 | 14 | 0 | 0 | 0 | silent_misdecode |

## Aggregate low-run boundary

### Phase shift -8 cycles
- correct_decode: delta -220 through -208 cycles

### Phase shift +0 cycles
- silent_misdecode: delta -220 through -216 cycles
- correct_decode: delta -215 through -208 cycles

### Phase shift +8 cycles
- silent_misdecode: delta -220 through -208 cycles

## Interpretation

This report compares isolated candidate firmware variants only. A candidate remains experimental until the complete regression, evidence contracts, and independent boundary tests validate its behavior.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`
Production firmware SHA-256: `5a61cb59f5ccfabe6c10e92fc70b94a8bf3da34a136b76e1cc6e07adecb2ac5a`
