# TRACEFORGE v0.2 — UART RX RTL Report

- Design: `morph_engine_v2`
- Reference: `MorphISAModelV2`
- Payload: `0xA6`
- Comparison: cycle-by-cycle state, PC, instruction, pin outputs, shift register, wait counter, timeout and fault
- Cases passed: 3/3

| Case | RTL/model match | Contract | Result | Final shift register | Error pin 7 |
|---|---|---|---|---|---|
| valid_a6 | True | True | PASS | 0x65 | False |
| bad_start_glitch | True | True | PASS | 0x00 | True |
| bad_stop_low | True | True | PASS | 0x65 | True |

## Scope

The UART RX RTL is run in Verilator and compared cycle-by-cycle against the independent reference model.
The final contract checks successful decoding of the valid A6 frame and error-flag pin behavior for the two corrupted frames.
This is simulation evidence, not physical silicon validation.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`
Original differential testbench SHA-256: `0f71679fa297d98829274ac8b33d1eb1147c633502a83bbd14e07df30768b9b5`

