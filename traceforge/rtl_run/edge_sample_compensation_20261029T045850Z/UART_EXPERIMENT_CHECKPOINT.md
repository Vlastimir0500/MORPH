# MORPH UART Experiment Checkpoint

Date: 2026-10-29

## Scope

These are isolated experimental UART receiver artifacts. They have
not been integrated into production MORPH RTL or firmware.

## Recorded results

1. Phase-tracker prototype: 7 cases passed. The fixed sampler failed
   the directed timing-drift waveform while edge re-anchoring decoded it.

2. Limitation matrix: 21 cases passed its intended criteria. Results
   showed edge re-anchoring helps dense transitions but does not by
   itself correct accumulated timing error across long edge-free runs.

3. Exhaustive byte sweep: 768 cases passed, testing all 256 byte values
   at transmitter periods of 38, 40, and 42 cycles. No decode failures,
   missing sample events, or data samples outside their expected cells
   were reported by that testbench.

4. Fault injection: 9 cases passed after correcting the testbench's
   sticky status monitor: one clean frame, one short false start, one
   malformed stop bit, and six single-cycle data-glitch positions.

## Limitations

These results are evidence for the isolated candidate and these specific
testbenches only. They are not a complete UART qualification, formal proof,
or evidence that production MORPH has the candidate's behavior.

Next: expand independent jitter and malformed-frame testing, validate
edge qualification, then consider integration only after regression passes.

## Production baseline

Production RTL SHA-256:
6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552

Production firmware SHA-256:
5a61cb59f5ccfabe6c10e92fc70b94a8bf3da34a136b76e1cc6e07adecb2ac5a
