# MORPH V2 engineering release checklist

## Source baseline

- Integrated physical branch: `research/morph-v2-final-integration`.
- Protected RTL SHA-256: `ebaad3f79ba71e2f958133a92d7d24a269396c161d89b4f51fda201d0895de98`.
- Protected UART firmware SHA-256: `5a61cb59f5ccfabe6c10e92fc70b94a8bf3da34a136b76e1cc6e07adecb2ac5a`.
- Physical configuration uses CTS4, 36 um clock-buffer spacing, PnR max fanout 6, signoff max fanout 8.

## Verification requirements

- All 154 Python/RTL regression tests must pass on the release commit.
- All 22 Cocotb tests must pass on the release commit.
- The six original GitHub engineering gates must pass on the release commit.
- Both SymbiYosys safety tasks must end in `PASS` on the same release commit.
- Physical signoff must report zero maximum-fanout, slew, and capacitance violations across fast, typical, and slow corners.
- All source changes since the protected RTL and firmware checksums must be reviewed.

## Reproduction

Run `bash formal/qualification/run.sh` in WSL using OSS CAD Suite. Check `build/formal/gating/status` and `build/formal/fault/status` for `PASS`. Keep generated logs out of Git commits.

## Release freeze

After CI success, record the exact commit SHA, signoff logs, formal proof logs, synthesized netlist, and GDS artifacts. Create an annotated tag only after inspecting all checks. Re-run CI if any release inputs change.

## Scope

A fully green engineering pipeline proves the specified checks passed. It does not demonstrate fabricated silicon behavior, unrestricted protocol compatibility, or any particular competition outcome. Document those separately.
