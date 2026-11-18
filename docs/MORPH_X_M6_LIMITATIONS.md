# MORPH X — verified claims and limitations (M6)

## Implemented and demonstrated in testbenches

- 8-pin digital input sampling/capture, with a bounded buffer of eight events.
- 32-bit event entries with 16-bit timestamp, changed-mask and sampled levels.
- Host readback and offline decode through the documented top-level controls.
- Host compilation of strict Temporal IR into V2 16-bit instructions.
- Single- and multi-pin time-constrained output replay on supported schedules.
- UART, SPI and I2C firmware demonstrations, with scoped digital timing tests.
- Four-pin Pulse Link and deterministic seeded protocol-neutral waveform
  demonstrations, verified with an independent expected-trace oracle.
- Offline Python reference model, Verilator RTL differential, Cocotb top-level,
  engine formal gating/fault proofs and IHP/LibreLane physical-design workflow.
- GDS output, precheck and post-route report checks for tested commits only.

## Unsupported or unproven

- **Not autonomous protocol identification or semantic understanding.** The
  host selects pins and generates firmware from observed edges or given IR.
- **Not an arbitrary waveform generator.** The single-issue V2 engine cannot
  issue multiple independent DRIVE instructions on exactly the same cycle.
  Exact gaps of one or three cycles are not representable; incompatible traces
  must be rejected rather than silently retimed.
- Capture buffer has 8 slots; overflow is a hard error. 16-bit timestamp
  rollover makes long gaps ambiguous, and readback interrupts capture.
- Replay is digital and relative to the first selected observed transition,
  not electrically synchronized to an external protocol master.
- Reprogramming is performed via the top-level host loader and reset.
  MORPH X does not autonomously rewrite its own instruction memory.
- No claims of USB/Ethernet compliance, analog performance, SPI/I2C standards
  certification, metastability MTBF, voltage compatibility, physical bus
  contention tolerance, or power/frequency measurements on fabricated silicon.
- The synthetic randomized Protocol Zero cases are **self-tests**, not a
  third-party blind challenge. The independent blind challenge is outstanding.
- Engine formal proof applies to specified safety assertions, not complete
  equivalence of every compiler or all capture hardware states.
- A successful GDS/precheck/STA flow does not imply a fabricated working chip.

## Citation-quality evidence principle

Quote the exact commit, workflow run ID, affected GDS artifact and formal
assertion when making a claim. Do not combine tests from one commit with
physical results from another. Do not count an automatically generated trace
as independent experimental data. Distinguish reproducibility evidence from
real-hardware measurements.
