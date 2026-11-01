# MORPH V2 Instruction Set Architecture

## Scope and machine model

This document defines the canonical 16-bit instruction encodings implemented by the V2 production RTL and its reference model.

- Instruction width: 16 bits.
- Program memory: 64 words, addressed by a 6-bit program counter (`PC`).
- Data pins: 8 digital pins, numbered 0 through 7.
- Opcode: `word[15:12]`.
- Unless an instruction assigns a meaning to a bit, that bit is reserved and **must be zero**.
- An instruction with a nonzero reserved bit, an invalid pin selector, an invalid loop encoding, or an unsupported opcode faults. A fault sets `fault`, clears all output enables (`pin_oe = 0`), and enters the terminal HALT state. The `pin_out` data register is not required to clear because its pins are disabled.

The assembler validates static branch targets against the emitted program image. The hardware has a fixed 64-word memory and does not receive the emitted program length as an input; `BRANCH` and `BRANCH_SAMPLE` therefore use their six-bit target directly. Firmware/image validation must ensure those targets identify intended instructions.

## Instruction encoding

Bits are shown as `[15:12] [11:8] [7:0]` unless a more specific field layout is shown. Hex masks identify bits which must be zero.

| Opcode | Mnemonic | Fields | Canonical constraints |
|---:|---|---|---|
| `0x0` | `HALT` | `[11:0]` unused | `[11:0] = 0`; reserved mask `0x0FFF` |
| `0x1` | `DRIVE` | `[11:8]` pin; `[0]` value | pin 0–7; `[7:1] = 0`; reserved mask `0x00FE` |
| `0x2` | `SAMPLE` | `[11:8]` pin | pin 0–7; `[7:0] = 0`; reserved mask `0x00FF` |
| `0x3` | `WAIT` | `[7:0]` cycle count | `[11:8] = 0`; reserved mask `0x0F00` |
| `0x4` | `EDGE` | `[11:8]` pin; `[7:1]` timeout; `[0]` direction | pin 0–7; timeout 0–127; direction 0=FALL, 1=RISE; no additional reserved bits |
| `0x5` | `SHIFT` | `[11:0]` unused | `[11:0] = 0`; reserved mask `0x0FFF` |
| `0x6` | `BRANCH` | `[5:0]` target | `[11:6] = 0`; reserved mask `0x0FC0` |
| `0x7` | `RELEASE` | `[11:8]` pin | pin 0–7; `[7:0] = 0`; reserved mask `0x00FF` |
| `0x8` | `BRANCH_SAMPLE` | `[7]` expected sample; `[5:0]` target | `[11:8] = 0` and `[6] = 0`; reserved mask `0x0F40` |
| `0x9` | `LOOP` | `[11:6]` count; `[5:0]` backward target | count 1–63; target must be less than the address of the LOOP instruction; all bits are assigned |
| `0xA` | `LOAD_IMM` | `[7:0]` immediate | `[11:8] = 0`; reserved mask `0x0F00` |
| `0xB` | `OD_SHIFT` | `[11:8]` pin | pin 0–7; `[7:0] = 0`; reserved mask `0x00FF` |
| `0xC` | `DRIVE_SHIFT` | `[11:8]` pin | pin 0–7; `[7:0] = 0`; reserved mask `0x00FF` |
| `0xD`–`0xF` | Reserved | None | Unsupported; always faults |

## Instruction semantics

### Pin and sample operations

- `DRIVE pin, value` writes `value` to the selected `pin_out` bit and sets that pin's output enable.
- `SAMPLE pin` copies the selected `pin_in` bit into the one-bit `sample_reg`.
- `SHIFT` shifts `shift_reg` left by one and inserts `sample_reg` into bit 0.
- `RELEASE pin` clears the selected output-enable bit and clears the selected `pin_out` bit.
- `LOAD_IMM immediate` loads the eight-bit immediate into `shift_reg`.
- `DRIVE_SHIFT pin` drives `shift_reg[7]` on the selected pin, enables that output, and shifts `shift_reg` left by one.
- `OD_SHIFT pin` implements open-drain-style serial output: it forces the selected `pin_out` bit low, sets output-enable when `shift_reg[7]` is zero (pull low), clears output-enable when it is one (release), and shifts `shift_reg` left by one.

### Timing and control flow

- `WAIT 0` advances immediately. `WAIT 1` through `WAIT 255` enter the wait state for the programmed count before advancing.
- `EDGE pin, direction, timeout` waits for the selected digital input transition. A timeout of zero means unbounded waiting; 1–127 is bounded. On bounded timeout, `timed_out` and `fault` assert, all pins are released, and execution halts.
- `BRANCH target` loads the six-bit target into `PC`.
- `BRANCH_SAMPLE expected, target` branches when `sample_reg` equals the encoded expected bit; otherwise it advances to the next instruction.
- `LOOP count, target` repeats the instruction region beginning at the backward target for the encoded count. The implementation supports one active counted loop; a nested or structurally conflicting loop faults and releases outputs.
- `HALT` enters the terminal halt state and **preserves existing pin output-enable/data values**. It does not implicitly release pins.

## Fault, reset, and programming behavior

- Invalid instruction encodings and unsupported opcodes set `fault`, clear `pin_oe`, and halt.
- A bounded `EDGE` timeout additionally sets `timed_out`.
- Active-low reset and `program_mode` reset execution state, clear `fault` and `timed_out`, and clear pin output enables. The program memory is retained across reset; writes occur through the programming interface while `rst_n` and `program_mode` are asserted.
- A canonical `HALT` is not a fault and does not clear output enables.

## Verification obligations

The assembler/disassembler, Python reference model, production RTL, and TinyTapeout RTL mirror must agree on this canonical encoding policy. The simulation tests exercise malformed reserved-bit patterns and unsupported opcodes after first enabling an output, then require a fault, terminal HALT, and all output enables cleared. Passing simulation and model/RTL differential tests are evidence for the tested cases, not a formal proof of all possible instruction streams.
