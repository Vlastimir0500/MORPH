# TRACEFORGE Protocol Checker Negative Controls v0.1

**Status:** PASS
**Scenarios:** 4/4 passed

The clean baseline must pass, while deliberately corrupted temporary trace copies must be rejected by their expected protocol checks.

| Scenario | Expected | Result | Targeted failure(s) detected |
|---|---|---|---|
| clean_baseline | PASS | PASS | — |
| flip_spi_mosi_bit | FAIL with targeted contract violation | REJECTED | SPI MOSI sequence |
| remove_i2c_slave_ack | FAIL with targeted contract violation | REJECTED | I2C slave ACK level |
| break_i2c_nack_line_release | FAIL with targeted contract violation | REJECTED | I2C NACK fault is signaled, I2C NACK releases SDA/SCL |

- Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`
- The three source trace JSON files were copied to a temporary workspace before mutation.
- No production RTL, checked-in trace, contract, or original regression result was changed by these negative controls.
- The I²C ACK is simulated testbench stimulus, not a real external slave measurement.
