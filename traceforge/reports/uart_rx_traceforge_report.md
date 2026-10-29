# TRACEFORGE UART RX Report

- Version: 0.1.0
- Payload: `0xA6`
- Nominal bit period: 436 cycles
- Validation: independent waveform contract; RTL not executed
- Cases meeting expectations: 4/4

| Case | Expected | Observed | Result | Decoded payload |
|---|---|---|---|---|
| valid_a6_frame | valid | valid | PASS | 0xA6 |
| bad_start_stuck_high | invalid | invalid | PASS | 0xA6 |
| bad_stop_stuck_low | invalid | invalid | PASS | 0xA6 |
| start_shortened_by_250_cycles | invalid | invalid | PASS | 0xD3 |

## Interpretation

A valid trace must have the expected total length, a low start-bit sample, eight binary data samples in LSB-first order, and a high stop-bit sample.
The shortened-start mutation is also checked against the nominal frame length.

This report validates waveform framing only. It does not establish that the MORPH RTL rejects these mutations or correctly receives the payload.

UART source SHA-256: `5142af4f5b79672bba45e26570b47a4c3dac6489d654e7e573d5e0835845e891`
UART HEX SHA-256: `5a61cb59f5ccfabe6c10e92fc70b94a8bf3da34a136b76e1cc6e07adecb2ac5a`
