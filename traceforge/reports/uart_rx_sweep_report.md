# TRACEFORGE v0.3 — UART Sweep

- Total cases: 15
- Passed: 15
- Failed: 0
- RTL compared cycle by cycle against `MorphISAModelV2`.
- Timing variations are exploratory; their payload results are recorded, not assumed.

| Case | RTL/model | Decoded | Pin-7 error | Contract | Result |
|---|---|---|---|---|---|
| payload_00 | True | 0x00 | False | True | PASS |
| payload_ff | True | 0xFF | False | True | PASS |
| payload_55 | True | 0xAA | False | True | PASS |
| payload_3c | True | 0x3C | False | True | PASS |
| payload_81 | True | 0x81 | False | True | PASS |
| payload_7e | True | 0x7E | False | True | PASS |
| payload_a5 | True | 0xA5 | False | True | PASS |
| bad_start_glitch | True | 0x00 | True | True | PASS |
| bad_stop_low | True | 0x65 | True | True | PASS |
| timing_period_416 | True | 0x65 | False | exploratory | PASS |
| timing_period_426 | True | 0x65 | False | exploratory | PASS |
| timing_period_431 | True | 0x65 | False | exploratory | PASS |
| timing_period_441 | True | 0x65 | False | exploratory | PASS |
| timing_period_446 | True | 0x65 | False | exploratory | PASS |
| timing_period_456 | True | 0x65 | False | exploratory | PASS |

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`

Timing sweep results measure this particular receiver implementation. They are not a general UART tolerance specification.
