import argparse
import json
import subprocess
import sys
from pathlib import Path


def generate_source(period):
    start_wait = period // 2 - 4
    first_data_wait = period - 6
    next_data_wait = period - 4

    waits = [start_wait, first_data_wait, next_data_wait]

    if any(value < 0 or value > 255 for value in waits):
        raise ValueError("Calculated WAIT value outside 0..255")

    lines = [
        "search:",
        "RX_CLEAR",
        "EDGE 0, FALL",
        f"WAIT {start_wait}",
        "SAMPLE 0",
        "BRANCH_SAMPLE 1, search",
        f"WAIT {first_data_wait}",
    ]

    for _ in range(8):
        lines.append("SAMPLE_SHIFT 0, RIGHT")
        lines.append(f"WAIT {next_data_wait}")

    lines.extend([
        "SAMPLE 0",
        "BRANCH_SAMPLE 0, search",
        "RX_COMMIT",
        "BRANCH search",
    ])

    if sum(1 for line in lines if line and not line.endswith(":")) != 26:
        raise ValueError("Unexpected instruction count")

    return "\n".join(lines) + "\n", {
        "bit_period": period,
        "start_wait": start_wait,
        "first_data_wait": first_data_wait,
        "subsequent_wait": next_data_wait,
        "instruction_count": 26,
        "program_capacity": 64,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bit-period", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    if not 8 <= args.bit_period <= 259:
        parser.error("Bit period must be between 8 and 259 cycles")

    output_dir = args.out_dir.resolve()
    assembler = Path(__file__).with_name("morph_assembler_v2.py")

    if output_dir.exists():
        parser.error(f"Output directory already exists: {output_dir}")

    if not assembler.is_file():
        parser.error(f"Assembler not found: {assembler}")

    source, metadata = generate_source(args.bit_period)

    output_dir.mkdir(parents=True)
    asm_path = output_dir / "uart_8n1_rx.asm"
    raw_path = output_dir / "program.raw.hex"
    program_path = output_dir / "program.hex"
    listing_path = output_dir / "program.lst"
    manifest_path = output_dir / "manifest.json"

    asm_path.write_text(source, encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(assembler),
            "assemble",
            str(asm_path),
            "-o",
            str(raw_path),
        ],
        check=True,
    )

    words = [
        int(line.strip(), 16)
        for line in raw_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    if len(words) != 26:
        raise RuntimeError(f"Expected 26 instructions, got {len(words)}")

    if any(word < 0 or word > 0xFFFF for word in words):
        raise RuntimeError("Invalid machine word")

    padded_words = words + [0] * (64 - len(words))
    program_path.write_text(
        "".join(f"{word:04X}\n" for word in padded_words),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(assembler),
            "disassemble",
            str(raw_path),
            "-o",
            str(listing_path),
        ],
        check=True,
    )

    metadata["machine_words"] = [f"{word:04X}" for word in words]
    metadata["padded_words"] = 64

    manifest_path.write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"UART_PROGRAM_GENERATED period={args.bit_period} "
        f"instructions={len(words)} capacity=64 "
        f"waits={metadata['start_wait']},"
        f"{metadata['first_data_wait']},"
        f"{metadata['subsequent_wait']}"
    )
    print(f"OUTPUT={output_dir}")


if __name__ == "__main__":
    main()
