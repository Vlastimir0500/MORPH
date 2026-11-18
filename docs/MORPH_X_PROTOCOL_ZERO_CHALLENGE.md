# Protocol Zero — impartial post-freeze demonstration protocol

This file is a **protocol for running a future blind challenge**, not evidence
that Protocol Zero has already been demonstrated.

1. Freeze final hardware and preserve exact Git SHA, ASIC netlist/GDS hashes,
   clock constraints and environment. Before selecting the challenge, publish
   a signed manifest/hash for hardware and tests.
2. Have an independent reviewer create an unfamiliar **digital** protocol
   specification **after** the freeze. Reviewers may not edit hardware RTL,
   GDS, ISA, verification model or the pre-committed hardware tests.
3. Publish the challenge specification, electrical roles, timing tolerances,
   the input stimulus and evaluation script before showing the compiler result.
4. Adapt only host-side IR, firmware and permitted protocol description files.
   If the hardware cannot produce required simultaneous edges, unsupported
   exact gaps, 1-wire analog electrical behavior etc., report the inability;
   do not reclassify a failure as success.
5. Verify via RTL top-level traces, gate-level if available, and ideally an
   independent physical-board target (if a fabricated ASIC exists). Record
   timing-error statistics, event loss, replay acceptance, run identifiers,
   all artifacts and hash matches.
6. Produce a reproducible evidence bundle linking input spec → IR → emitted
   firmware → target trace → independent evaluation → Git SHA/GDS hash.

## Why this is separate

Protocol inference, controlled challenges, target hardware acceptance and an
unknown-after-freeze test cannot be declared complete from synthetic fixtures
prepared during compiler development. The present M4 package adds a versatile
replay compiler and a limited SPI-like scheduling demonstration only.
