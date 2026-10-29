# TRACEFORGE SPI/I2C Simulation Evidence

- Source: fresh TinyTapeout V2 Cocotb run
- XML testcases: 15
- Suite failures: 0
- Required protocol cases passed: 3/3
- Production RTL and TinyTapeout engine identical: True

| Protocol | Test | Result | Source assertions | Engine matches production RTL |
|---|---|---|---|---|
| SPI | test_spi_mode0_a5_waveform | PASS | True | True |
| I2C | test_i2c_address_probe_ack_stop | PASS | True | True |
| I2C | test_i2c_nack_releases_bus | PASS | True | True |

The evidence records the outcomes of the named Cocotb tests in this run. It also verifies that the test source contains the expected protocol assertions.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`
TinyTapeout engine SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`
Test source SHA-256: `6cb91158d4fd5c3a071b6e944dfcc3fbdfc820ed5db2b5c3133869364ce55ea3`

