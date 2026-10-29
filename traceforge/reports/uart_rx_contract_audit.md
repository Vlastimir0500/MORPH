# TRACEFORGE — UART Contract Audit

- Common measured correct-decode ranges: `[[413, 460]]` cycles
- In-envelope matrix cases: 384
- In-envelope cases passed: 384
- Cases outside the envelope: 184
- Contract violations: 0
- Minimized nonuniform counterexample symbol durations outside the envelope: [3, 5, 6, 7]

The common period range is based on the tested payload/timing matrix. It is empirical evidence for this particular receiver demonstration, not a universal UART timing guarantee.

Cases outside the measured envelope remain exploratory; the contract does not require them to be decoded or flagged.
