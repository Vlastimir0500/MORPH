import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer


async def initialize(dut):
    dut.clk.value = 0
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await ClockCycles(dut.clk, 3)
    await Timer(1, unit="ns")
    dut.rst_n.value = 1
    await Timer(1, unit="ns")


async def write_byte(dut, address, value, high_byte):
    dut.ui_in.value = 0x80 | (0x40 if high_byte else 0) | (address & 0x3F)
    dut.uio_in.value = value & 0xFF
    await ClockCycles(dut.clk, 1)
    await Timer(1, unit="ns")


async def write_word(dut, address, word):
    await write_byte(dut, address, word & 0xFF, False)
    await write_byte(dut, address, (word >> 8) & 0xFF, True)


async def start_program(dut, pin_value=0):
    dut.ui_in.value = 0
    dut.uio_in.value = pin_value
    await Timer(1, unit="ns")


@cocotb.test()
async def test_all_eight_output_pins(dut):
    await initialize(dut)
    await write_word(dut, 0, 0x1701)
    await write_word(dut, 1, 0x0000)
    await start_program(dut)
    await ClockCycles(dut.clk, 2)
    await Timer(1, unit="ns")
    assert int(dut.uio_oe.value) == 0x80
    assert int(dut.uio_out.value) & 0x80
    assert int(dut.uo_out.value) == 0


@cocotb.test()
async def test_release_selected_pin(dut):
    await initialize(dut)
    await write_word(dut, 0, 0x1301)
    await write_word(dut, 1, 0x7300)
    await write_word(dut, 2, 0x0000)
    await start_program(dut)
    await ClockCycles(dut.clk, 2)
    await Timer(1, unit="ns")
    assert int(dut.uio_oe.value) == 0x08
    assert int(dut.uio_out.value) & 0x08
    await ClockCycles(dut.clk, 2)
    await Timer(1, unit="ns")
    assert int(dut.uio_oe.value) == 0
    assert int(dut.uio_out.value) & 0x08 == 0


@cocotb.test()
async def test_sample_shift_and_input_bus(dut):
    await initialize(dut)
    await write_word(dut, 0, 0x2500)
    await write_word(dut, 1, 0x5000)
    await write_word(dut, 2, 0x0000)
    await start_program(dut, 0x20)
    await ClockCycles(dut.clk, 4)
    await Timer(1, unit="ns")
    assert int(dut.uo_out.value) == 1


@cocotb.test()
async def test_six_bit_program_address(dut):
    await initialize(dut)
    await write_word(dut, 0, 0x6030)
    await write_word(dut, 48, 0x1701)
    await write_word(dut, 49, 0x0000)
    await start_program(dut)
    await ClockCycles(dut.clk, 4)
    await Timer(1, unit="ns")
    assert int(dut.uio_oe.value) == 0x80
    assert int(dut.uio_out.value) & 0x80


@cocotb.test()
async def test_sample_conditioned_branch_taken(dut):
    await initialize(dut)
    await write_word(dut, 0, 0x2500)
    await write_word(dut, 1, 0x8083)
    await write_word(dut, 2, 0x1101)
    await write_word(dut, 3, 0x1201)
    await write_word(dut, 4, 0x0000)
    await start_program(dut, 0x20)
    await ClockCycles(dut.clk, 6)
    await Timer(1, unit="ns")
    assert int(dut.uio_oe.value) == 0x04


@cocotb.test()
async def test_bounded_edge_timeout_releases_all_pins(dut):
    await initialize(dut)
    await write_word(dut, 0, 0x1001)
    await write_word(dut, 1, 0x420F)
    await write_word(dut, 2, 0x1401)
    await write_word(dut, 3, 0x0000)
    await start_program(dut, 0)
    await ClockCycles(dut.clk, 13)
    await Timer(1, unit="ns")
    assert int(dut.uio_oe.value) == 0


@cocotb.test()
async def test_unimplemented_opcode_fails_safe(dut):
    await initialize(dut)
    await write_word(dut, 0, 0x9000)
    await start_program(dut)
    await ClockCycles(dut.clk, 3)
    await Timer(1, unit="ns")
    assert int(dut.uio_oe.value) == 0
