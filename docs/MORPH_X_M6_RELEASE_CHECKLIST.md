# MORPH X — M6 release qualification checklist

This checklist accompanies **MORPH X M6**, based on the proven M5 source tag
`morph-x-protocol-lab-v0.6`. It is a verification and reproducibility milestone,
not a declaration that silicon has been fabricated or that an external blind
Protocol Zero exercise has occurred.

## Required, exact-commit release gates

1. Confirm the protected `rtl/morph_engine_v2.sv` and
   `protocols/v2_uart_rx_a6.hex` SHA256 hashes match the verified baseline;
   verify the TinyTapeout engine mirror is byte-identical. The capture RTL,
   top module, and source lists must be present.
2. Run `python3 scripts/morph_x_m6_release.py audit --strict`, which emits
   `build/morph-x-m6/source-audit.json`. A release-source failure blocks M6.
   The cleanup report is **read-only**; no directory is automatically removed.
3. Run `python -m pytest -q sim`, including the M6 release-test negatives.
   Every test must pass, without unsupported tool skips.
4. Run complete TinyTapeout Cocotb tests with Icarus, including all M5
   hardware-level tests. Confirm no skipped/failed/error cases.
5. Commit only M6 documentation, tests, audit tool, and the workflow/README
   updates. **Do not commit `build/`, intermediate logs or runtime caches.**
6. For this exact commit, confirm GitHub `MORPH Engineering Gates` succeeds
   with six jobs: `rtl-regression`, `tinytapeout-rtl`, `gds`, `precheck`,
   `gate-level-test`, and `Final post-route physical gate`. Confirm separate
   `MORPH V2 Formal Qualification` succeeds with `formal-qualification`.
7. Run the existing unified full qualification runner against the **new
   M6 engineering GDS run**, not an older M5 artifact:

   ```bash
   python scripts/run_full_qualification.py \
     --github-run-id ENGINEERING_RUN_ID \
     --output build/qualification/qualification-report.json
   ```

   Any `BLOCKED` stage means **INCOMPLETE**, not PASS. Check the combined
   JSON and the copied GDS reports. This runner performs the engine CDC
   structural checks, synthesis, source/contract checks, Cocotb, and physical
   report checks, but does not replace vendor tapeout checks.
8. Fetch exact-commit CI evidence through GitHub CLI:

   ```bash
   python scripts/morph_x_m6_release.py check-ci \
     --engineering ENGINEERING_RUN_ID \
     --formal FORMAL_RUN_ID
   ```

9. Re-run `python scripts/morph_x_m6_release.py audit --strict` after the
   M6 commit. Assemble a provenance bundle:

   ```bash
   python scripts/morph_x_m6_release.py bundle
   ```

   This requires all three reports to reference the same Git commit and
   returns a ZIP at `build/morph-x-m6/morph-x-m6-evidence.zip`.
10. Create an annotated M6 tag only when every gate above is green. Do not
    tag a partially verified commit or represent an unrun blind evaluation
    as complete.

## Cleanup approach

`backups/`, `traceforge/`, older formal experiments, and the first TinyTapeout
project may contain important development or physical evidence. The audit
classifies these directories for review, **not deletion**. After M6 is
qualified, create a separate cleanup branch, inspect references from active
sources, preserve important artifacts and frozen tags, then remove redundant
tracked artifacts selectively. Re-run all gates on the cleaned commit.

## Explicit outstanding tasks outside this automated gate

- A **blind external Protocol Zero** challenge with an independently provided
  waveform and non-self-generated observed replay evidence.
- Optional physical fabrication, silicon bring-up, timing/power measurements,
  electrical compliance, and board-level tests (none are claimed by M6).
- Competition submission by the repository owner, including honest disclosure
  of AI-assisted development and adherence to official contest terms.
