import argparse
from pathlib import Path

from morph_assembler_v2 import assemble


def build_source(address, data_bytes, half_period=58):
    if not isinstance(address, int) or not 0 <= address <= 0x7F:
        raise ValueError("I2C address must be a 7-bit integer from 0 to 127")
    if not isinstance(data_bytes, (list, tuple)) or not 1 <= len(data_bytes) <= 2:
        raise ValueError("this V2 program supports one or two payload bytes")
    if not isinstance(half_period, int) or not 1 <= half_period <= 255:
        raise ValueError("half_period must be from 1 to 255")
    for value in data_bytes:
        if not isinstance(value, int) or not 0 <= value <= 0xFF:
            raise ValueError("each payload byte must be an integer from 0 to 255")

    lines = [
        "RELEASE 2",
        "RELEASE 1",
        "WAIT 2",
        "DRIVE 1, 0",
        "WAIT 2",
        "DRIVE 2, 0",
    ]

    transaction_bytes = [address << 1, *data_bytes]
    for index, value in enumerate(transaction_bytes):
        label = f"byte_{index}_bits"
        lines.extend([
            f"LOAD_IMM 0x{value:02X}",
            f"{label}: OD_SHIFT 1",
            f"WAIT {half_period}",
            "RELEASE 2",
            f"WAIT {half_period}",
            "DRIVE 2, 0",
            f"LOOP 8, {label}",
            "RELEASE 1",
            f"WAIT {half_period}",
            "RELEASE 2",
            f"WAIT {half_period}",
            "SAMPLE 1",
            "DRIVE 2, 0",
            "BRANCH_SAMPLE 1, nack",
        ])

    lines.extend([
        "DRIVE 1, 0",
        "WAIT 2",
        "RELEASE 2",
        "WAIT 2",
        "RELEASE 1",
        "HALT",
        "nack: DRIVE 7, 1",
        "RELEASE 2",
        "RELEASE 1",
        "HALT",
    ])
    return "\n".join(lines) + "\n"


def build_program(address, data_bytes, half_period=58):
    source = build_source(address, data_bytes, half_period)
    words = assemble(source)
    if len(words) > 64:
        raise ValueError(f"generated I2C program uses {len(words)} words; limit is 64")
    return source, words


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--data", required=True, nargs="+", type=lambda value: int(value, 0))
    parser.add_argument("--half-period", type=int, default=58)
    parser.add_argument("--source-out")
    parser.add_argument("--hex-out")
    args = parser.parse_args()

    try:
        source, words = build_program(args.address, args.data, args.half_period)
    except (ValueError, TypeError) as exc:
        parser.error(str(exc))

    if args.source_out:
        Path(args.source_out).write_text(source, encoding="utf-8")
    if args.hex_out:
        Path(args.hex_out).write_text("".join(f"{word:04X}\n" for word in words), encoding="utf-8")
    if not args.source_out and not args.hex_out:
        print("".join(f"{word:04X}\n" for word in words), end="")
    print(f"Generated {len(words)} words for address 0x{args.address:02X} and {len(args.data)} data byte(s).")


if __name__ == "__main__":
    main()
