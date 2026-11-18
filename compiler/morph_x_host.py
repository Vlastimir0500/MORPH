"""MORPH X host-side trace readback protocol.

The caller supplies an async read_register(ui_in_byte) operation for the
particular transport. No USB/UART/physical host adapter is implied.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from morph_x_trace import CAPACITY, decode_capture, read_command


async def read_capture_async(read_register: Callable[[int], Awaitable[int]]) -> dict:
    """Read a stable bounded capture frame using the chip's top-level pin map.

    The caller MUST put ui_in[7]=0 and allow this routine to choose ui_in[6:0].
    This routine is not a substitute for proper bus electrical handling.
    """
    async def byte_at(address: int) -> int:
        value = await read_register(address)
        if type(value) is not int or not 0 <= value <= 255:
            raise ValueError("read_register must return an 8-bit integer")
        return value

    status = await byte_at(read_command(status=True))
    count = status & 0x0F
    if status & 0x80 or count > CAPACITY or bool(status & 0x20) != (count == CAPACITY):
        raise ValueError("invalid initial capture status")

    slots = []
    for slot in range(count):
        slots.append([await byte_at(read_command(slot, page)) for page in range(4)])

    # Ignore bit 6 (primed) which can fall after read_mode first takes effect.
    # Count, full and overflow must not change during the transaction.
    final_status = await byte_at(read_command(status=True))
    if (status & 0xBF) != (final_status & 0xBF):
        raise ValueError("capture status changed during readback")
    frame = {"status": final_status, "slots": slots}
    decode_capture(frame)  # fail closed on malformed or incoherent captured data
    return frame
