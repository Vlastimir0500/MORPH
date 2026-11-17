import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "compiler"))
from morph_x_trace import decode_capture, read_command, to_vcd


def test_command_map():
    assert read_command(status=True) == 0x60
    assert read_command(0, 0) == 0x40
    assert read_command(7, 3) == 0x5F
    for slot, page in [(-1, 0), (8, 0), (0, -1), (0, 4)]:
        with pytest.raises(ValueError):
            read_command(slot, page)


def test_decode_and_vcd():
    decoded = decode_capture({"status": 0x42, "slots": [
        [0x01, 0x01, 0x07, 0x00],
        [0x03, 0x02, 0x0A, 0x00],
    ]})
    assert decoded["count"] == 2 and not decoded["overflow"]
    assert decoded["events"][1]["delta_cycles"] == 3
    waveform = to_vcd(decoded)
    assert "#140\nb00000001 !" in waveform
    assert "#200\nb00000011 !" in waveform


def test_wrap_and_full():
    decoded = decode_capture({"status": 0x38, "slots": [
        [i & 0xFF, 1, (65534 + i) & 0xFF, ((65534 + i) & 0xFFFF) >> 8]
        for i in range(8)
    ]})
    assert decoded["full"] and decoded["overflow"]
    assert decoded["events"][2]["delta_cycles"] == 1


@pytest.mark.parametrize("frame", [
    {"status": 0xFF, "slots": []},
    {"status": 0x21, "slots": [[1, 1, 0, 0]]},
    {"status": 0x02, "slots": [[1, 1, 0, 0]]},
    {"status": 0x01, "slots": [[1, 0, 0, 0]]},
    {"status": 0x01, "slots": [[1, 1, 256, 0]]},
    {"status": 0x02, "slots": [[1, 1, 0, 0], [0, 1, 0, 0]]},
])
def test_malformed_capture_rejected(frame):
    with pytest.raises(ValueError):
        decode_capture(frame)
