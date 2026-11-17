"""MORPH X captured-event register map, decoder, and VCD waveform exporter.

This is an offline decoder: hardware access remains the responsibility of the
host transport. Captures are intentionally bounded to eight events.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

CAPACITY = 8
CLOCK_HZ = 50_000_000


def read_command(slot: int = 0, page: int = 0, *, status: bool = False) -> int:
    if status:
        return 0x60
    if not 0 <= slot < CAPACITY or not 0 <= page < 4:
        raise ValueError("slot must be 0..7 and page 0..3")
    return 0x40 | (page << 3) | slot


@dataclass(frozen=True)
class TraceEvent:
    timestamp: int
    changed: int
    levels: int
    delta_cycles: int


def decode_capture(frame: dict) -> dict:
    status = frame["status"]
    if type(status) is not int or not 0 <= status <= 255:
        raise ValueError("status must be one byte")
    if status & 0x80:
        raise ValueError("reserved status bit is set")
    count = status & 0x0F
    overflow = bool(status & 0x10)
    full = bool(status & 0x20)
    if count > CAPACITY or full != (count == CAPACITY):
        raise ValueError("inconsistent count/full status")
    slots = frame["slots"]
    if not isinstance(slots, list) or len(slots) != count:
        raise ValueError("slots must contain exactly count entries")
    events = []
    previous = None
    for i, row in enumerate(slots):
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError(f"slot {i} must contain four bytes")
        if any(type(value) is not int or not 0 <= value <= 255 for value in row):
            raise ValueError(f"slot {i} contains an invalid byte")
        levels, changed, low, high = row
        if not changed:
            raise ValueError("empty transition mask in recorded event")
        timestamp = (high << 8) | low
        delta = 0 if previous is None else (timestamp - previous) & 0xFFFF
        if previous is not None and delta == 0:
            raise ValueError("duplicate timestamp (capture is one event per cycle)")
        events.append(TraceEvent(timestamp, changed, levels, delta))
        previous = timestamp
    return {"count": count, "full": full, "overflow": overflow,
            "primed": bool(status & 0x40),
            "events": [asdict(event) for event in events]}


def to_vcd(decoded: dict, *, clock_hz: int = CLOCK_HZ) -> str:
    if clock_hz <= 0 or 1_000_000_000 % clock_hz:
        raise ValueError("clock_hz must evenly divide 1 GHz")
    step_ns = 1_000_000_000 // clock_hz
    result = ["$date", "  generated from MORPH X captured events", "$end",
              "$version MORPH X offline capture decoder $end",
              "$timescale 1ns $end", "$scope module morph_x $end",
              "$var wire 8 ! pins $end", "$var wire 8 \" changed $end",
              "$upscope $end", "$enddefinitions $end", "#0", "bx !", "b0 \""]
    absolute_cycles = 0
    for i, event in enumerate(decoded["events"]):
        absolute_cycles += event["delta_cycles"] if i else event["timestamp"]
        result.extend([f"#{absolute_cycles * step_ns}",
                       f"b{event['levels']:08b} !",
                       f"b{event['changed']:08b} \""])
    return "\n".join(result) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Decode MORPH X capture readback")
    parser.add_argument("input", type=Path, help="JSON with status and slots")
    parser.add_argument("--vcd", type=Path, help="Export GTKWave-compatible waveform")
    parser.add_argument("--clock-hz", type=int, default=CLOCK_HZ)
    args = parser.parse_args()
    decoded = decode_capture(json.loads(args.input.read_text()))
    print(json.dumps(decoded, indent=2))
    if args.vcd:
        args.vcd.write_text(to_vcd(decoded, clock_hz=args.clock_hz))


if __name__ == "__main__":
    main()
