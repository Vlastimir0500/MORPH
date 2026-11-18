# Protocol Zero independent evaluation evidence checklist

**Status when this file is created: NOT YET A BLIND PASS.**

To qualify a future externally selected Protocol Zero challenge:

- [ ] Freeze and publish verified Git commit/tag and hashes for RTL, netlist,
  GDS, compiler, testbench and acceptance oracle.
- [ ] Identify an independent reviewer and record challenge-selection time
  strictly **after** freeze.
- [ ] Record challenge JSON and immutable SHA256 *before* compilation.
- [ ] Save raw input capture, including all 8 byte slots and status/overflow.
- [ ] If capture is not used, document the direct IR entry route explicitly.
- [ ] Compile to program.hex without modifying hardware or acceptance oracle.
- [ ] Save cycle-by-cycle `uio_out/uio_oe` evidence from an independent RTL
  testbench, gate-level simulation, or fabricated-device capture.
- [ ] Use `judge` to check exact timing, pin, value, output-enable release,
  fault state and unselected-output enabling.
- [ ] Publish all rejected cases: coincident edges, 1/3-cycle gaps, buffer
  overflow, capture gaps, 16-bit counter wrap ambiguity.
- [ ] Publish simulator/hardware logs, git SHA, tool versions, scripts and
  reproducible invocation; distinguish simulation and physical silicon.
- [ ] Obtain independent reviewer acceptance; no self-test is substituted.

If an item cannot be completed, write **NOT VERIFIED** rather than PASS.
