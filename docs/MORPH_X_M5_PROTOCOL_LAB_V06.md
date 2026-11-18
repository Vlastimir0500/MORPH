# MORPH X M5 — Protocol Lab V0.6 (candidate)

M5 extends the frozen **M4 V2-ISA multi-pin backend** with a protocol-neutral
benchmark contract, independent digital transition oracle, randomized
four-line waveform challenges, and top-level pin-to-pin capture/replay tests.
This package **does not modify RTL, protected firmware, ISA, GDS, or formal**.

## Results are not interchangeable

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| M4 model verification | Generated instructions implement exact relative transitions in the existing V2 model | Fabricated chip operation |
| M5 independent oracle | An independently supplied digital edge list matches the supplied *observed trace*, including release and fault flags | Authenticity of the supplied observation, analog compliance, peripheral interoperability |
| Cocotb top-level test | Actual simulated `uio_in` capture, `uo_out` readback, host program and `uio_out/uio_oe` replay | Protocol Zero **blind** trial or physical silicon |
| Existing V2 protocol regressions | Specific RTL waveform patterns and error/release handling | Exhaustive UART/SPI/I2C standard certification |
| External Protocol Zero trial | **Only if** post-freeze challenger authors input and evaluator independently after freeze | Not demonstrated by our own seeded fixtures |

### Existing certified-under-test protocol examples

- UART TX `0xA5`, RX `0xA6`, seven RX patterns, invalid start/stop rejection.
- SPI TX Mode 0/1/2/3 for the tested `0xA5` frame.
- I2C tested write/probe/ACK/NACK and safe-release cases to `0x50`.
- M4 coordinated 2-pin capture and 3-pin SPI-*like* waveform. These remain
  distinct from cross-vendor protocol interoperability claims.
- M5 adds an 8-edge, 4-pin request/data/clock/ack `PULSE-LINK` **toy waveform**
  and seeded permutations with different exact cycle gaps.

### Run M5 candidate checks

```bash
python -m pytest -q sim/test_morph_x_protocol_zero.py sim/test_morph_x_protocol_zero_rtl.py -v
python -m pytest -q sim
cd tinytapeout-template-v2/test
# Use your established Cocotb 3.12 / PYTHONHOME=/usr procedure; target 31 tests
```

For a synthetic challenge that explicitly **does not count** as an independent
blind trial:

```bash
python compiler/morph_x_protocol_zero.py generate-selftest --seed 23456 --output build/m5/selftest.json
python compiler/morph_x_protocol_zero.py prepare build/m5/selftest.json --output-dir build/m5/firmware
```

To prepare a challenge from an external reviewer **after a frozen tagged
hardware/software manifest**:

```bash
python compiler/morph_x_protocol_zero.py prepare challenger.json \
  --capture measured_capture.json --output-dir build/m5/reviewer
python compiler/morph_x_protocol_zero.py judge challenger.json \
  measured_replay.json --output build/m5/reviewer/judge.report.json
```

The reviewer must supply `challenger.json`, capture measured actual bytes,
produce a measured output trace and validate the observer independently. A
**model report alone never constitutes a Protocol Zero pass**. Exit code 0
means input accepted and firmware model-qualified, NOT blind success. Judgment
exit codes: 0 exact observation match, 1 well-formed mismatch, 2 invalid input.

### Challenge contract

`examples/morph_x_pulse_link_challenge.json` is a publicly known *self-test*.
It specifies `schema`, `challenge_id`, `clock_hz=50000000`, ascending `pins`,
`initial_levels` mask, and `events`, each `{cycle,pin,value}`. The first event
is relative cycle 0. Up to 8 captures, no noise-loss guarantee, digital input
levels only; source capture can be checked with `--capture`.

The oracle's observation schema is
`morph-x.protocol-zero.observation.v1`, with exactly `schema`,
`challenge_id`, `source` (`rtl-top`, `gate-level`, `physical`, or
`offline-synthetic`), `transitions`, `released`, `fault`, and
`unselected_output_enable_seen`. The oracle compares **exact relative edge
cycles and values** against the source spec (not against a model-generated
expected trace). A boolean source label is not provenance proof. Run logs,
Git SHA, toolchain versions and genuine simulator/hardware observation remain
required for independently auditable evidence.

### Unsupported conditions and honest failure

- Simultaneous selected pin changes require atomic multi-pin drive; V2 lacks it.
- Inter-DRIVE gaps of **1 or 3** cycles are impossible in this V2 schedule.
- More than eight capture events per frame exceed the current capture FIFO.
- The host-driven compile/program loop is not autonomous on silicon.
- Timestamps are modulo 65536; full-wrap ambiguity cannot be detected.
- Input capture observes synchronized pins, whereas replay uses digital outputs;
  pullups, signal strength, analog slew, setup/hold, bus electrical rules and
  mixed-voltage protocols require separate electrical validation.
- Initial/terminal output-enable events and bus turnarounds are not equivalent
  to captured digital transitions.
- Self-authored test vectors, even randomly seeded, do **not** count as an
  unknown-after-freeze external challenge.

### Reviewer challenge integrity

Before an external trial, preserve the final `feat/morph-x` commit, exact tag,
RTL hashes, GDS hash, all CI run IDs, test code and tool versions. Have a third
party select an unknown challenge **after** that freeze and save a challenge
SHA256 before compiling. Disallow changes to protected RTL, testbench, model,
ISA and acceptance oracle. Permit only spec translation to IR and firmware;
publish all rejected schedules rather than omitting them. Record observed
raw trace, oracle report, reproducible commands and an independent signoff.
