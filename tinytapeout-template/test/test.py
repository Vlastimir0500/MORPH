import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer

PROGRAM_MODE = 0x40
BYTE_WRITE = 0x10
HIGH_BYTE = 0x20


async def reset_dut(dut, pin_input=0):
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    await Timer(1, unit="ns")
    dut.uio_in.value = pin_input
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    await Timer(1, unit="ns")


async def initialize(dut):
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)


async def load_word(dut, address, word):
    address &= 0x0F
    dut.ui_in.value = PROGRAM_MODE | BYTE_WRITE | address
    dut.uio_in.value = word & 0xFF
    await ClockCycles(dut.clk, 1)
    await Timer(1, unit="ns")
    dut.ui_in.value = PROGRAM_MODE | BYTE_WRITE | HIGH_BYTE | address
    dut.uio_in.value = (word >> 8) & 0xFF
    await ClockCycles(dut.clk, 1)
    await Timer(1, unit="ns")
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    await ClockCycles(dut.clk, 1)
    await Timer(1, unit="ns")


@cocotb.test()
async def test_bytewise_load_executes_set_pin(dut):
    await initialize(dut)
    await load_word(dut, 0, 0x1001)
    await reset_dut(dut)
    await ClockCycles(dut.clk, 5)
    await Timer(1, unit="ns")
    assert int(dut.uio_out.value) & 1 == 1, "SET instruction did not drive pin_out high"
    assert int(dut.uio_oe.value) & 1 == 1, "Output enable not asserted in execution mode"


@cocotb.test()
async def test_orphan_high_byte_does_not_overwrite_instruction(dut):
    await initialize(dut)
    await load_word(dut, 0, 0x1001)
    dut.ui_in.value = PROGRAM_MODE | BYTE_WRITE | HIGH_BYTE
    dut.uio_in.value = 0x00
    await ClockCycles(dut.clk, 1)
    await Timer(1, unit="ns")
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    await reset_dut(dut)
    await ClockCycles(dut.clk, 5)
    await Timer(1, unit="ns")
    assert int(dut.uio_out.value) & 1 == 1, "Orphan high-byte write unexpectedly changed the instruction"


@cocotb.test()
async def test_sample_then_shift_instruction_sequence(dut):
    await initialize(dut)
    await load_word(dut, 0, 0x2000)
    await load_word(dut, 1, 0x5000)
    await reset_dut(dut, pin_input=1)
    await ClockCycles(dut.clk, 8)
    await Timer(1, unit="ns")
    assert int(dut.uo_out.value) & 1 == 1, "Sample/shift sequence did not shift the sampled input into output"

@cocotb.test()
async def test_temporal_contract_matches_wrapper_rtl(dut):
    import json
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "compiler"))
    from morph_assembler import assemble

    contract_path = root / "protocols" / "edge_timed_release.contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    scenario = contract["temporal_scenarios"][0]
    source_path = contract_path.parent / contract["source"]
    words = assemble(source_path.read_text(encoding="utf-8"))

    await initialize(dut)
    for address, word in enumerate(words):
        await load_word(dut, address, word)

    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    await Timer(1, unit="ns")
    dut.rst_n.value = 1
    await Timer(1, unit="ns")

    observed = {"pin_out_transitions": [], "shift_reg_transitions": []}
    previous_output = 0
    previous_shift = 0

    for offset, pin_value in enumerate(scenario["pin_trace"], start=2):
        dut.uio_in.value = pin_value
        await ClockCycles(dut.clk, 1)
        await Timer(1, unit="ns")
        output_value = int(dut.uio_out.value) & 1
        shift_value = int(dut.uo_out.value)

        if output_value != previous_output:
            observed["pin_out_transitions"].append(
                {"cycle": offset, "value": output_value}
            )
        if shift_value != previous_shift:
            observed["shift_reg_transitions"].append(
                {"cycle": offset, "value": shift_value}
            )

        previous_output = output_value
        previous_shift = shift_value

    for signal, expected_events in scenario["expect"].items():
        assert observed[signal] == expected_events, (
            f"{scenario['name']} {signal} mismatch: "
            f"expected {expected_events}, observed {observed[signal]}"
        )
