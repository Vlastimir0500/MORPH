"""Transport-agnostic host register readback tests."""
import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))

from morph_x_host import read_capture_async
from morph_x_trace import read_command


def test_readout_exact_sequence_and_capture_contents():
    expected_slots = [[1, 1, 7, 0], [0, 1, 13, 0], [1, 1, 19, 0]]
    commands = []
    async def reader(address):
        commands.append(address)
        if address == read_command(status=True):
            return 0x43
        slot, page = address & 7, (address >> 3) & 3
        return expected_slots[slot][page]
    frame = asyncio.run(read_capture_async(reader))
    assert frame == {"status": 0x43, "slots": expected_slots}
    assert commands == [read_command(status=True)] + [
        read_command(slot, page) for slot in range(3) for page in range(4)
    ] + [read_command(status=True)]


def test_changed_readback_status_fails_closed():
    n = 0
    async def reader(address):
        nonlocal n
        if address == read_command(status=True):
            n += 1
            return 0x42 if n == 1 else 0x43
        return 0
    with pytest.raises(ValueError, match="changed during readback"):
        asyncio.run(read_capture_async(reader))


@pytest.mark.parametrize("bad_value", [0x81, 0x49, -1, 256, True])
def test_invalid_status_fails_closed(bad_value):
    async def reader(address):
        return bad_value
    with pytest.raises(ValueError, match="initial capture status|8-bit integer"):
        asyncio.run(read_capture_async(reader))


def test_mutated_record_rejected():
    async def reader(address):
        if address == read_command(status=True):
            return 0x41
        page = (address >> 3) & 3
        return [1, 0, 7, 0][page]  # zero changed mask is forbidden
    with pytest.raises(ValueError, match="empty transition mask"):
        asyncio.run(read_capture_async(reader))
