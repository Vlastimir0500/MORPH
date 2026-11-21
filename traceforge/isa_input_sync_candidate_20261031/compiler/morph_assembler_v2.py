import argparse
import re
from pathlib import Path

PROGRAM_DEPTH = 64
WORD_BITS = 16
WORD_MASK = 0xFFFF

OPCODES = {
    "HALT": 0x0,
    "DRIVE": 0x1,
    "SAMPLE": 0x2,
    "WAIT": 0x3,
    "EDGE": 0x4,
    "SHIFT": 0x5,
    "BRANCH": 0x6,
    "RELEASE": 0x7,
    "BRANCH_SAMPLE": 0x8,
    "LOOP": 0x9,
    "LOAD_IMM": 0xA,
    "OD_SHIFT": 0xB,
    "DRIVE_SHIFT": 0xC,
    "SAMPLE_SHIFT": 0xD,
    "RX_CLEAR": 0xE,
    "RX_COMMIT": 0xF,
}

OPCODE_NAMES = {v: k for k, v in OPCODES.items()}
LABEL_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")


class AssemblyError(ValueError):
    pass


def parse_integer(token):
    try:
        return int(token, 16) if token.lower().startswith("0x") else int(token, 10)
    except ValueError as exc:
        raise AssemblyError(f"invalid integer: {token}") from exc


def parse_source(source):
    labels = {}
    instructions = []

    for line_number, original in enumerate(source.splitlines(), 1):
        line = original.split(";", 1)[0].split("#", 1)[0].strip()
        if not line:
            continue

        match = LABEL_PATTERN.match(line)
        if match:
            label, remainder = match.groups()
            if label in labels:
                raise AssemblyError(f"line {line_number}: duplicate label '{label}'")
            labels[label] = len(instructions)
            line = remainder.strip()
            if not line:
                continue

        instructions.append((line_number, line))
        if len(instructions) > PROGRAM_DEPTH:
            raise AssemblyError(f"line {line_number}: program exceeds {PROGRAM_DEPTH} instruction words")

    return labels, instructions


def _number(token, low, high, field, line_number):
    value = parse_integer(token)
    if not low <= value <= high:
        raise AssemblyError(f"line {line_number}: {field} must be from {low} to {high}")
    return value


def _target(token, labels, instruction_count, line_number):
    value = labels[token] if token in labels else parse_integer(token)
    if not 0 <= value < instruction_count:
        raise AssemblyError(
            f"line {line_number}: branch target must identify an instruction from 0 to {instruction_count - 1}"
        )
    return value


def assemble(source):
    labels, instructions = parse_source(source)
    words = []
    count = len(instructions)

    for address, (line_number, line) in enumerate(instructions):
        parts = [p for p in re.split(r"[\s,]+", line.strip()) if p]
        mnemonic = parts[0].upper()
        operands = parts[1:]

        if mnemonic not in OPCODES:
            raise AssemblyError(f"line {line_number}: unsupported instruction '{mnemonic}'")

        opcode = OPCODES[mnemonic]
        word = opcode << 12

        if mnemonic in ("HALT", "SHIFT", "RX_CLEAR", "RX_COMMIT"):
            if operands:
                raise AssemblyError(f"line {line_number}: {mnemonic} takes no operands")

        elif mnemonic == "DRIVE":
            if len(operands) != 2:
                raise AssemblyError(f"line {line_number}: DRIVE requires pin and value")
            pin = _number(operands[0], 0, 7, "pin", line_number)
            value = _number(operands[1], 0, 1, "drive value", line_number)
            word |= (pin << 8) | value

        elif mnemonic == "SAMPLE":
            if len(operands) != 1:
                raise AssemblyError(f"line {line_number}: SAMPLE requires a pin")
            pin = _number(operands[0], 0, 7, "pin", line_number)
            word |= pin << 8

        elif mnemonic == "WAIT":
            if len(operands) != 1:
                raise AssemblyError(f"line {line_number}: WAIT requires a cycle count")
            cycles = _number(operands[0], 0, 255, "WAIT cycles", line_number)
            word |= cycles

        elif mnemonic == "EDGE":
            if len(operands) not in (2, 3):
                raise AssemblyError(f"line {line_number}: EDGE requires pin, RISE/FALL and optional timeout")
            pin = _number(operands[0], 0, 7, "pin", line_number)
            direction = operands[1].upper()
            if direction not in ("RISE", "FALL"):
                raise AssemblyError(f"line {line_number}: EDGE direction must be RISE or FALL")
            timeout = 0
            if len(operands) == 3 and operands[2].upper() != "FOREVER":
                timeout = _number(operands[2], 0, 127, "EDGE timeout", line_number)
            word |= (pin << 8) | (timeout << 1) | (1 if direction == "RISE" else 0)

        elif mnemonic == "BRANCH":
            if len(operands) != 1:
                raise AssemblyError(f"line {line_number}: BRANCH requires one target")
            word |= _target(operands[0], labels, count, line_number)

        elif mnemonic == "RELEASE":
            if len(operands) != 1:
                raise AssemblyError(f"line {line_number}: RELEASE requires a pin")
            pin = _number(operands[0], 0, 7, "pin", line_number)
            word |= pin << 8

        elif mnemonic == "BRANCH_SAMPLE":
            if len(operands) != 2:
                raise AssemblyError(f"line {line_number}: BRANCH_SAMPLE requires value and target")
            value = _number(operands[0], 0, 1, "sample value", line_number)
            target = _target(operands[1], labels, count, line_number)
            word |= (value << 7) | target

        elif mnemonic == "LOOP":
            if len(operands) != 2:
                raise AssemblyError(f"line {line_number}: LOOP requires count and backward target")
            loop_count = _number(operands[0], 1, 63, "loop count", line_number)
            target = _target(operands[1], labels, count, line_number)
            if target >= address:
                raise AssemblyError(f"line {line_number}: LOOP target must be an earlier instruction")
            word |= (loop_count << 6) | target

        elif mnemonic == "LOAD_IMM":
            if len(operands) != 1:
                raise AssemblyError(f"line {line_number}: LOAD_IMM requires one 8-bit immediate")
            immediate = _number(operands[0], 0, 255, "LOAD_IMM immediate", line_number)
            word |= immediate

        elif mnemonic in ("OD_SHIFT", "DRIVE_SHIFT"):
            if len(operands) != 1:
                raise AssemblyError(f"line {line_number}: {mnemonic} requires one pin")
            pin = _number(operands[0], 0, 7, "pin", line_number)
            word |= pin << 8

        elif mnemonic == "SAMPLE_SHIFT":
            if len(operands) not in (1, 2):
                raise AssemblyError(f"line {line_number}: SAMPLE_SHIFT requires a pin and optional direction")
            pin = _number(operands[0], 0, 7, "pin", line_number)
            direction = operands[1].upper() if len(operands) == 2 else "LEFT"
            if direction not in ("LEFT", "RIGHT"):
                raise AssemblyError(f"line {line_number}: SAMPLE_SHIFT direction must be LEFT or RIGHT")
            word |= pin << 8
            if direction == "RIGHT":
                word |= 1

        words.append(word)

    return words


def disassemble(words):
    if len(words) > PROGRAM_DEPTH:
        raise AssemblyError(f"program exceeds {PROGRAM_DEPTH} instruction words")

    result = []
    for address, word in enumerate(words):
        if not isinstance(word, int) or not 0 <= word <= WORD_MASK:
            raise AssemblyError(f"word at address {address} is not a 16-bit value")

        opcode = (word >> 12) & 0xF
        selector = (word >> 8) & 0xF
        low = word & 0xFF
        name = OPCODE_NAMES.get(opcode)

        if name is None:
            raise AssemblyError(f"address {address}: unsupported opcode 0x{opcode:X}")

        if name in ("HALT", "SHIFT", "RX_CLEAR", "RX_COMMIT"):
            if word != opcode << 12:
                raise AssemblyError(f"address {address}: invalid {name} encoding")
            text = name

        elif name == "DRIVE":
            if selector > 7 or low & 0xFE:
                raise AssemblyError(f"address {address}: invalid DRIVE encoding")
            text = f"DRIVE {selector}, {low & 1}"

        elif name == "SAMPLE":
            if selector > 7 or low != 0:
                raise AssemblyError(f"address {address}: invalid SAMPLE encoding")
            text = f"SAMPLE {selector}"

        elif name == "WAIT":
            if selector != 0:
                raise AssemblyError(f"address {address}: invalid WAIT encoding")
            text = f"WAIT {low}"

        elif name == "EDGE":
            if selector > 7:
                raise AssemblyError(f"address {address}: invalid EDGE pin")
            timeout = (low >> 1) & 0x7F
            direction = "RISE" if low & 1 else "FALL"
            text = f"EDGE {selector}, {direction}" if timeout == 0 else f"EDGE {selector}, {direction}, {timeout}"

        elif name == "BRANCH":
            target = word & 0x3F
            if word & 0x0FC0 or target >= len(words):
                raise AssemblyError(f"address {address}: invalid BRANCH encoding or target")
            text = f"BRANCH {target}"

        elif name == "RELEASE":
            if selector > 7 or low != 0:
                raise AssemblyError(f"address {address}: invalid RELEASE encoding")
            text = f"RELEASE {selector}"

        elif name == "LOOP":
            loop_count = (word >> 6) & 0x3F
            target = word & 0x3F
            if loop_count == 0 or target >= address:
                raise AssemblyError(f"address {address}: invalid LOOP encoding or non-backward target")
            text = f"LOOP {loop_count}, {target}"

        elif name == "BRANCH_SAMPLE":
            target = word & 0x3F
            if word & 0x0F40 or target >= len(words):
                raise AssemblyError(f"address {address}: invalid BRANCH_SAMPLE encoding or target")
            text = f"BRANCH_SAMPLE {(word >> 7) & 1}, {target}"

        elif name == "LOAD_IMM":
            if selector != 0:
                raise AssemblyError(f"address {address}: invalid LOAD_IMM encoding")
            text = f"LOAD_IMM {low}"

        elif name in ("OD_SHIFT", "DRIVE_SHIFT"):
            if selector > 7 or low != 0:
                raise AssemblyError(f"address {address}: invalid {name} encoding")
            text = f"{name} {selector}"

        elif name == "SAMPLE_SHIFT":
            if selector > 7 or (low & 0xFE) != 0:
                raise AssemblyError(f"address {address}: invalid {name} encoding")
            text = f"{name} {selector}, RIGHT" if low & 1 else f"{name} {selector}"

        result.append(text)

    return result


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    asm = subparsers.add_parser("assemble")
    asm.add_argument("source")
    asm.add_argument("-o", "--output")
    dis = subparsers.add_parser("disassemble")
    dis.add_argument("input")
    dis.add_argument("-o", "--output")
    args = parser.parse_args()

    try:
        if args.command == "assemble":
            words = assemble(Path(args.source).read_text(encoding="utf-8"))
            output = "".join(f"{word:04X}\n" for word in words)
        else:
            raw = Path(args.input).read_text(encoding="utf-8").splitlines()
            words = []
            for line_number, line in enumerate(raw, 1):
                line = line.split(";", 1)[0].strip()
                if line:
                    try:
                        words.append(int(line, 16))
                    except ValueError as exc:
                        raise AssemblyError(f"line {line_number}: expected hexadecimal word") from exc
            output = "\n".join(disassemble(words)) + ("\n" if words else "")
    except (OSError, AssemblyError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
