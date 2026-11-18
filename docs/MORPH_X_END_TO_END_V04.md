# MORPH X M3: top-level capture-to-replay qualification

Status: **unverified until real Cocotb, Python, gate-level, formal, GDS, and physical gates complete on the new SHA**.

## Intended observation path

1. Program one HALT word using standard V2 16-bit loader on TinyTapeout inputs.
2. Hold all output enables low; stimulate `uio_in` at known cycle offsets.
3. Retrieve the actual captured status and 4-byte event records through the combinational `uo_out` readback using the `ui_in` register map.
4. Validate the bounded trace using `morph_x_host.read_capture_async` and the existing decoder.
5. Translate the trace to a single-pin Temporal IR, compile 16-bit V2 replay words, and run the reference-model scheduler.
6. Program those **generated** words through the standard top-level loader.
7. On the same top-level interface, check `uio_out`, `uio_oe`, exact relative transition offsets, absence of unexpected driven pins and final release.

Two Cocotb scenarios exercise pin 0 and pin 5, including an unselected pin changing in the background. Python transport tests check the register transaction order, incomplete/changed status and malformed records.

## Important limitations

- Replays *only selected pin*, not the unrelated pin, which is intentionally used to demonstrate trace filtering.
- Timing is only compared **relative to the first selected input transition**, not absolute phase/alignment with capture.
- Captured events refer to **synchronized digital input** values, while replay is a driven digital output. No electrical loopback to an actual external device is claimed.
- A read temporarily pauses capture; the 8-event store is bounded. Counter wraps and gaps cannot always be disambiguated.
- Physical tests are simulations/GDS-flow evidence, not fabricated-silicon measurements.
- No chip modification. Full multi-pin synchronized replay, inference, triggers, and protocol zero are separate milestones.
- Formal gating and fault properties remain those of the V2 safety suite; they do not establish a full compiler-correctness proof.

## Regression acceptance

`python -m pytest -q sim` must pass (expected **195** tests: previous 187 + eight added transport tests; actual count controls). The TinyTapeout top-level `make` suite must pass **26** tests (previous 24 + two end-to-end tests) for both RTL and gate-level simulation. Formal qualification, GDS, precheck and physical gates must be green on the **same** commit SHA before tagging.

If a test fails, do not edit protected `rtl/morph_engine_v2.sv` or `protocols/v2_uart_rx_a6.hex`; investigate test timing/transport or branch changes first.
