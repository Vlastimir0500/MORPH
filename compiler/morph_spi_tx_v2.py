import argparse
from pathlib import Path

from morph_assembler_v2 import assemble


def build_source(mode, data, half_period=20):
    if not isinstance(mode, int) or mode not in range(4):
        raise ValueError("SPI mode must be 0, 1, 2, or 3")
    if not isinstance(data, int) or not 0 <= data <= 0xFF:
        raise ValueError("SPI data must be an integer from 0 to 255")
    if not isinstance(half_period, int) or not 1 <= half_period <= 255:
        raise ValueError("half_period must be from 1 to 255")

    cpol = (mode >> 1) & 1
    cpha = mode & 1
    leading = 1 - cpol
    lines = [
        "DRIVE 0, 0",
        f"DRIVE 2, {cpol}",
        f"LOAD_IMM 0x{data:02X}",
    ]

    if cpha == 0:
        lines.extend([
            "bit_loop: DRIVE_SHIFT 1",
            f"WAIT {half_period}",
            f"DRIVE 2, {leading}",
            f"WAIT {half_period}",
            f"DRIVE 2, {cpol}",
            "LOOP 8, bit_loop",
        ])
    else:
        lines.extend([
            f"bit_loop: DRIVE 2, {leading}",
            "DRIVE_SHIFT 1",
            f"WAIT {half_period}",
            f"DRIVE 2, {cpol}",
            f"WAIT {half_period}",
            "LOOP 8, bit_loop",
        ])

    lines.extend(["DRIVE 0, 1", "HALT"])
    return "\n".join(lines) + "\n"


def build_program(mode, data, half_period=20):
    source = build_source(mode, data, half_period)
    words = assemble(source)
    if len(words) > 64:
        raise ValueError(f"generated SPI program uses {len(words)} words; limit is 64")
    return source, words


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, type=int)
    parser.add_argument("--data", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--half-period", type=int, default=20)
    parser.add_argument("--source-out")
    parser.add_argument("--hex-out")
    args = parser.parse_args()
    try:
        source, words = build_program(args.mode, args.data, args.half_period)
    except ValueError as exc:
        parser.error(str(exc))
    if args.source_out:
        Path(args.source_out).write_text(source, encoding="utf-8")
    if args.hex_out:
        Path(args.hex_out).write_text("".join(f"{word:04X}\n" for word in words), encoding="utf-8")
    if not args.source_out and not args.hex_out:
        print("".join(f"{word:04X}\n" for word in words), end="")
    print(f"Generated {len(words)} words for SPI Mode {args.mode}, data 0x{args.data:02X}.")


if __name__ == "__main__":
    main()
