# MORPH X unified design / engineering acceptance specification

Status: target architecture and dependency plan, **not implemented functionality**.
Baseline: verified MORPH V2, commit `f4c69ce7e292b6948ac4565ee6e25d534a9ea430`.

## One architecture, one evidence chain

A protocol definition or captured trace becomes a typed temporal IR. An IR
scheduler either creates a legal V2-compatible or extended microprogram, or
rejects it with a concrete reason. The exact emitted firmware is checked by an
independent simulator and the RTL. The hardware engine drives protocol pins,
while the trace unit timestamps sampled inputs. The host retrieves traces,
converts them to standard waveforms, identifies protocol structure and produces
replay candidates. Timing/error perturbations are described through the same IR,
and the evidence pipeline records assumptions, cycles, waveforms, test results,
formal proofs, physical constraints and tool versions for a single Git SHA.

### Hardware planes

1. **Temporal execution:** existing 64×16 instruction store and 13-opcode ISA.
   Add only minimally necessary timing primitives and retain canonical V2
   programs as a regression set.
2. **Capture and observation:** synchronized digital inputs, event detection,
   timestamps, bounded storage, status and host readback. First slice stores
   8 events; capacity is an area/timing optimization, not a promise.
3. **Pin fabric:** eight bidirectional protocol pins, programmable roles,
   open-drain behavior, output enable interlocks and fault release. Enforce
   absence of contention between host and protocol controls.
4. **Safety/timing:** reset, programming interlocks, bounded edge waits,
   defensive fault handling and documented setup/hold constraints.
5. **Host control:** mode selection, safe programming, status, capture readout,
   trace reconstruction, and, where feasible, streaming or triggered capture.

### Host software planes

1. **Temporal DSL / IR:** operation identifiers, pin sets, signed or unsigned
   deadlines, ordering, cycles, bounded loops, branching, sample conditions,
   legal electrical role and failure conditions.
2. **Compiler / validation:** strict schema, memory size validation, timing
   scheduling, independent tool to reject unsupported operations, exact
   emitted words and a versioned manifest.
3. **Capture decoder / replay:** decode statuses, timestamps and transitions;
   generate VCD and interoperable CSV; use RTL differential tests to prove
   event-to-ISA replay meets the specified cycle tolerances.
4. **Trace analysis / inference:** host-side hypotheses only. Show confidence,
   alternative clock/baud guesses, raw observations and failure conditions.
5. **Evidence dashboard:** source commit, firmware hash, compiler version,
   reference-model cycle results, formal assertions, utilization, physical
   signoff and waveforms, without inventing measurements.

## Protocol portfolio

- Baseline: UART RX/TX, SPI modes 0–3, I²C address/probe/write patterns.
- Stronger scenarios: back-to-back transactions, edge variation, malformed
  responses, timeout recovery and reset/reprogram safe behavior.
- New software-defined demonstrations: JTAG state sequencing, SWD turnaround,
  PS/2, 1-Wire. Their **real** supported role and timing must be demonstrated.
- Conditional, if resources allow: CAN with external transceiver; selected
  low-speed USB and 10 Mbit Ethernet digital encodings. Not certification.
- **Protocol Zero:** an unknown protocol authored only after the hardware RTL
  and GDS are frozen. Compiler may change; chip RTL and GDS may not.

## Dependency and release gates

| Gate | Acceptance criterion |
| ---- | ---- |
| V2 fallback | Verified, immutable tag pointing at f4c69ce7e292 |
| M1 Trace prototype | 2 new Cocotb tests + 9 decoder tests; original 22 pass; synthesizes |
| M2 Trace physical closure | 8×4 allocation passes TinyTapeout, gated netlist and strict physical checks |
| M3 Shared Temporal IR | Independent parser, schema, deterministic compiler, negative tests |
| M4 Replay / timing | Cycle-exact model/RTL differential; verify recorded event tolerance |
| M5 Dynamic protocol features | Several diverse protocols running without RTL changes |
| M6 Safety qualification | Existing 2 formal proofs + new invariants; no unfounded assumptions |
| M7 Protocol Zero | Post-freeze DSL-only adaptation; independent trace evidence |
| M8 Release | GDS, STA, gate-level, precheck, formal, timing, docs, demo from same SHA |

No gate is automatically passed because an earlier version or a partial
simulation passed. Physical area and timing results for MORPH X are **unknown**
until the new hardware is hardened and inspected.

## Prioritization rule

Every new feature must improve the central thesis (a single silicon fabric
adapting to multiple protocols), have an executable demonstration, and fit the
silicon budget. A better verified unknown-protocol demonstration outranks
many unsupported claims about known protocols. Hardware changes stop before
submission freeze; host tooling and evidence then receive final attention.
