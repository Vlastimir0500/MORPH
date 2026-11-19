# MORPH X README — figure provenance

All assets in this directory are new and included as source-controlled relative paths. They are not vendor-provided masks or fabricated-chip micrographs.

- `hero.jpg`: original AI-assisted **concept artwork** illustrating a programmable digital fabric; NOT a render from the GDS, KLayout, a foundry, or a fabricated die. Editorial text overlay was added programmatically.
- `real-gds.png`: framed, proportionally resized crop of user-provided **KLayout screenshot (2783)** showing the actual routed `tt_um_rattandeep_morph_v2` GDS. Original GDS geometry is not modified. Source screenshot seen November 19, 2026.
- `layout-inspection.png`: cropped detail from user-provided **KLayout screenshot (2782)** plus recorded GDS hierarchy metrics from local inspection. No physical regions are assigned speculative module names.
- `architecture.svg`: newly drawn explanatory system diagram grounded in repository docs; diagram is **logical**, not mask placement.
- `isa.svg`: newly drawn compact reference view of 13 opcodes. `docs/isa_v2.md` is the authoritative machine specification.
- `verification.svg`: original visualization of exact-commit CI and local test results; consult live GitHub Actions for current status.
- `pulse-link.gif`: programmatic animation of the actual self-test **challenge specification** in `examples/morph_x_pulse_link_challenge.json`; NOT measured hardware trace or independent unknown-protocol validation.
- `pipeline.gif`: conceptual animated host/hardware processing stages, not recorded device operation.
- `mark.svg`: original vector logo.

**GDS local evidence:** `tt_um_rattandeep_morph_v2.klayout.gds`; SHA-256 `bb10938c0c726c51100c609c28cec6b08c030907d438dcc1e6b0243a442e6472`; top prBoundary 1724.16 × 710.64 µm. Exact provenance to GitHub CI artifacts not established by matching hash.

No font binaries are included with the graphics. SVG uses system font fallbacks; raster images embed glyph pixels only.
