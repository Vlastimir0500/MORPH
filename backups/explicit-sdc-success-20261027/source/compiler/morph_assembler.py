import argparse
import re
from pathlib import Path

PROGRAM_DEPTH = 16
WORD_BITS = 16
WORD_MASK = (1 << WORD_BITS) - 1

OPCODES = {
    "DRIVE": 0x1,
    "SAMPLE": 0x2,
    "WAIT": 0x3,
    "EDGE": 0x4,
    "SHIFT": 0x5,
    "BRANCH": 0x6,
}

OPCODE_NAMES = {value: key for key, value in OPCODES.items()}
LABEL_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")


class AssemblyError(ValueError):
    pass


def parse_integer(token):
    try:
        if token.lower().startswith("0x"):
            return int(token, 16)
        return int(token, 10)
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
                raise AssemblyError(
                    f"line {line_number}: duplicate label '{label}'"
                )

            labels[label] = len(instructions)
            line = remainder.strip()

            if not line:
                continue

        instructions.append((line_number, line))

        if len(instructions) > PROGRAM_DEPTH:
            raise AssemblyError(
                f"line {line_number}: program exceeds "
                f"{PROGRAM_DEPTH} instruction words"
            )

    return labels, instructions


def assemble(source):
    labels, instructions = parse_source(source)
    words = []

    for line_number, line in instructions:
        parts = re.split(r"[\s,]+", line.strip())
        mnemonic = parts[0].upper()
        operands = parts[1:]

        if mnemonic not in OPCODES:
            raise AssemblyError(
                f"line {line_number}: unsupported instruction '{mnemonic}'"
            )

        opcode = OPCODES[mnemonic]
        arg = 0

        if mnemonic == "DRIVE":
            if len(operands) != 1:
                raise AssemblyError(
                    f"line {line_number}: DRIVE requires value 0 or 1"
                )
            arg = parse_integer(operands[0])
            if arg not in (0, 1):
                raise AssemblyError(
                    f"line {line_number}: DRIVE value must be 0 or 1"
                )

        elif mnemonic == "SAMPLE":
            if operands:
                raise AssemblyError(
                    f"line {line_number}: SAMPLE takes no operands"
                )

        elif mnemonic == "WAIT":
            if len(operands) != 1:
                raise AssemblyError(
                    f"line {line_number}: WAIT requires a cycle count"
                )
            arg = parse_integer(operands[0])
            if not 0 <= arg <= 255:
                raise AssemblyError(
                    f"line {line_number}: WAIT range is 0 to 255"
                )

        elif mnemonic == "EDGE":
            if len(operands) != 1:
                raise AssemblyError(
                    f"line {line_number}: EDGE requires RISE or FALL"
                )
            edge = operands[0].upper()
            if edge not in ("RISE", "FALL"):
                raise AssemblyError(
                    f"line {line_number}: EDGE requires RISE or FALL"
                )
            arg = 1 if edge == "RISE" else 0

        elif mnemonic == "SHIFT":
            if operands:
                raise AssemblyError(
                    f"line {line_number}: SHIFT takes no operands"
                )

        elif mnemonic == "BRANCH":
            if len(operands) != 1:
                raise AssemblyError(
                    f"line {line_number}: BRANCH requires a label or address"
                )

            target = operands[0]
            if target in labels:
                arg = labels[target]
            else:
                arg = parse_integer(target)

            if not 0 <= arg < len(instructions):
                raise AssemblyError(
                    f"line {line_number}: branch target must identify "
                    f"an instruction in this program"
                )

        words.append((opcode << 12) | arg)

    return words


def disassemble(words):
    if len(words) > PROGRAM_DEPTH:
        raise AssemblyError(
            f"program exceeds {PROGRAM_DEPTH} instruction words"
        )

    result = []

    for address, word in enumerate(words):
        if not isinstance(word, int) or not 0 <= word <= WORD_MASK:
            raise AssemblyError(
                f"word at address {address} is not a 16-bit value"
            )

        opcode = (word >> 12) & 0xF
        selector = (word >> 8) & 0xF
        arg = word & 0xFF
        mnemonic = OPCODE_NAMES.get(opcode)

        if mnemonic is None:
            raise AssemblyError(
                f"address {address}: unsupported opcode 0x{opcode:X}"
            )

        if selector != 0:
            raise AssemblyError(
                f"address {address}: nonzero selector is unsupported "
                f"by the current single-pin prototype"
            )

        if mnemonic == "DRIVE":
            if arg not in (0, 1):
                raise AssemblyError(
                    f"address {address}: invalid DRIVE encoding"
                )
            text = f"DRIVE {arg}"

        elif mnemonic == "SAMPLE":
            if arg != 0:
                raise AssemblyError(
                    f"address {address}: invalid SAMPLE encoding"
                )
            text = "SAMPLE"

        elif mnemonic == "WAIT":
            text = f"WAIT {arg}"

        elif mnemonic == "EDGE":
            if arg not in (0, 1):
                raise AssemblyError(
                    f"address {address}: invalid EDGE encoding"
                )
            text = "EDGE RISE" if arg else "EDGE FALL"

        elif mnemonic == "SHIFT":
            if arg != 0:
                raise AssemblyError(
                    f"address {address}: invalid SHIFT encoding"
                )
            text = "SHIFT"

        else:
            if arg & 0xF0:
                raise AssemblyError(
                    f"address {address}: invalid BRANCH encoding"
                )
            if arg >= len(words):
                raise AssemblyError(
                    f"address {address}: branch target {arg} "
                    f"is outside the program"
                )
            text = f"BRANCH {arg}"

        result.append(text)

    return result


def read_hex_file(path):
    words = []

    for line_number, original in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        line = original.split(";", 1)[0].strip()
        if not line:
            continue

        try:
            word = int(line, 16)
        except ValueError as exc:
            raise AssemblyError(
                f"{path}:{line_number}: expected a hexadecimal word"
            ) from exc

        if not 0 <= word <= WORD_MASK:
            raise AssemblyError(
                f"{path}:{line_number}: word exceeds 16 bits"
            )

        words.append(word)

    return words


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    assemble_parser = subparsers.add_parser("assemble")
    assemble_parser.add_argument("source")
    assemble_parser.add_argument("-o", "--output")

    disassemble_parser = subparsers.add_parser("disassemble")
    disassemble_parser.add_argument("input")
    disassemble_parser.add_argument("-o", "--output")

    args = parser.parse_args()

    try:
        if args.command == "assemble":
            words = assemble(
                Path(args.source).read_text(encoding="utf-8")
            )
            output = "".join(f"{word:04X}\n" for word in words)
        else:
            words = read_hex_file(args.input)
            output = "".join(
                f"{line}\n" for line in disassemble(words)
            )

        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            print(output, end="")

    except (AssemblyError, OSError) as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
