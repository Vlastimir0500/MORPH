import cocotb
import sys
from pathlib import Path
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer, RisingEdge

ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "protocols").is_dir())
sys.path.insert(0, str(ROOT / "compiler"))
from morph_i2c_write_v2 import build_program
from morph_spi_tx_v2 import build_program as build_spi_program


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

    # Hold the engine in reset while the two-stage input
    # synchronizer captures the initial external pin state.
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    await Timer(1, unit="ns")

    dut.rst_n.value = 1
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


@cocotb.test()
async def test_uart_tx_a5_waveform(dut):
    await initialize(dut)
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / "protocols").is_dir())
    program = root / "protocols" / "v2_uart_tx_a5.hex"
    words = [int(line.strip(), 16) for line in program.read_text().splitlines() if line.strip()]
    assert len(words) == 31
    for address, word in enumerate(words):
        await write_word(dut, address, word)
    await start_program(dut)

    cycle = 0
    start_cycle = None
    last_value = None
    transitions = []
    sample_offsets = [218, 654, 1090, 1526, 1962, 2398, 2834, 3270, 3706, 4142]
    samples = {}

    for _ in range(4500):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        cycle += 1
        oe = int(dut.uio_oe.value) & 1
        value = int(dut.uio_out.value) & 1

        if not oe:
            continue

        if start_cycle is None:
            start_cycle = cycle
            last_value = value
            assert value == 0

        offset = cycle - start_cycle

        if offset in sample_offsets:
            samples[offset] = value

        if value != last_value:
            transitions.append((offset, value))
            last_value = value

    expected_transitions = [
        (436, 1),
        (872, 0),
        (1308, 1),
        (1744, 0),
        (2616, 1),
        (3052, 0),
        (3488, 1),
    ]
    assert transitions == expected_transitions, f"Transitions: {transitions}"

    expected_samples = dict(zip(sample_offsets, [0, 1, 0, 1, 0, 0, 1, 0, 1, 1]))
    assert samples == expected_samples, f"Sampled frame: {samples}"
    assert int(dut.uio_oe.value) & 1 == 1
    assert int(dut.uio_out.value) & 1 == 1
    dut._log.info("PASS: UART frame decoded as 0xA5, start and stop bits valid")


@cocotb.test()
async def test_uart_rx_a6_frame(dut):
    await initialize(dut)
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / "protocols").is_dir())
    program = root / "protocols" / "v2_uart_rx_a6.hex"
    words = [int(line.strip(), 16) for line in program.read_text().splitlines() if line.strip()]
    assert len(words) == 18

    for address, word in enumerate(words):
        await write_word(dut, address, word)

    await start_program(dut, pin_value=1)
    await ClockCycles(dut.clk, 10)
    await Timer(1, unit="ns")
    dut.uio_in.value = 0

    bit_period = 436
    await ClockCycles(dut.clk, bit_period)
    await Timer(1, unit="ns")

    data = 0xA6
    for bit_index in range(8):
        dut.uio_in.value = (data >> bit_index) & 1
        await ClockCycles(dut.clk, bit_period)
        await Timer(1, unit="ns")

    dut.uio_in.value = 1
    await ClockCycles(dut.clk, 240)
    await Timer(1, unit="ns")

    observed = int(dut.uo_out.value)
    assert observed == 0x65, f"Expected shift register 0x65, got 0x{observed:02X}"
    assert int(dut.uio_oe.value) == 0, f"Unexpected output enable: 0x{int(dut.uio_oe.value):02X}"


@cocotb.test()
async def test_uart_rx_multiple_data_patterns(dut):
    await initialize(dut)
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / "protocols").is_dir())
    program = root / "protocols" / "v2_uart_rx_a6.hex"
    words = [int(line.strip(), 16) for line in program.read_text().splitlines() if line.strip()]
    assert len(words) == 18

    for address, word in enumerate(words):
        await write_word(dut, address, word)

    patterns = [0x00, 0xFF, 0x55, 0x3C, 0x81, 0x7E, 0xA5]
    bit_period = 436

    for data in patterns:
        dut.ui_in.value = 0
        dut.uio_in.value = 1
        dut.rst_n.value = 0
        await ClockCycles(dut.clk, 3)
        await Timer(1, unit="ns")
        dut.rst_n.value = 1
        await Timer(1, unit="ns")
        await ClockCycles(dut.clk, 10)
        await Timer(1, unit="ns")

        dut.uio_in.value = 0
        await ClockCycles(dut.clk, bit_period)
        await Timer(1, unit="ns")

        for bit_index in range(8):
            dut.uio_in.value = (data >> bit_index) & 1
            await ClockCycles(dut.clk, bit_period)
            await Timer(1, unit="ns")

        dut.uio_in.value = 1
        await ClockCycles(dut.clk, 240)
        await Timer(1, unit="ns")

        expected = int(f"{data:08b}"[::-1], 2)
        observed = int(dut.uo_out.value)
        assert observed == expected, f"Input 0x{data:02X}: expected 0x{expected:02X}, got 0x{observed:02X}"
        assert int(dut.uio_oe.value) == 0, f"Input 0x{data:02X}: unexpected error output enable 0x{int(dut.uio_oe.value):02X}"

    dut._log.info("PASS: UART RX decoded seven data patterns with no error flags")


@cocotb.test()
async def test_uart_rx_rejects_bad_start(dut):
    await initialize(dut)
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / "protocols").is_dir())
    program = root / "protocols" / "v2_uart_rx_a6.hex"
    words = [int(line.strip(), 16) for line in program.read_text().splitlines() if line.strip()]
    assert len(words) == 18

    for address, word in enumerate(words):
        await write_word(dut, address, word)

    await start_program(dut, pin_value=1)
    await ClockCycles(dut.clk, 10)
    dut.uio_in.value = 0
    await ClockCycles(dut.clk, 60)
    dut.uio_in.value = 1

    for _ in range(500):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        oe = int(dut.uio_oe.value)
        out = int(dut.uio_out.value)
        if oe & 0x80:
            assert oe == 0x80, f"Unexpected output enables: 0x{oe:02X}"
            assert out & 0x80, "Bad-start error marker must be high"
            dut._log.info("PASS: UART receiver rejects an invalid start bit")
            return

    raise AssertionError("UART receiver did not flag the invalid start bit")


@cocotb.test()
async def test_uart_rx_rejects_bad_stop(dut):
    await initialize(dut)
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / "protocols").is_dir())
    program = root / "protocols" / "v2_uart_rx_a6.hex"
    words = [int(line.strip(), 16) for line in program.read_text().splitlines() if line.strip()]
    assert len(words) == 18

    for address, word in enumerate(words):
        await write_word(dut, address, word)

    await start_program(dut, pin_value=1)
    await ClockCycles(dut.clk, 10)
    dut.uio_in.value = 0
    bit_period = 436
    await ClockCycles(dut.clk, bit_period)
    await Timer(1, unit="ns")

    data = 0xA6
    for bit_index in range(8):
        dut.uio_in.value = (data >> bit_index) & 1
        await ClockCycles(dut.clk, bit_period)
        await Timer(1, unit="ns")

    dut.uio_in.value = 0

    for _ in range(500):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        oe = int(dut.uio_oe.value)
        out = int(dut.uio_out.value)
        if oe & 0x80:
            assert oe == 0x80, f"Unexpected output enables: 0x{oe:02X}"
            assert out & 0x80, "Bad-stop error marker must be high"
            dut._log.info("PASS: UART receiver rejects an invalid stop bit")
            return

    raise AssertionError("UART receiver did not flag the invalid stop bit")


@cocotb.test()
async def test_spi_mode0_a5_waveform(dut):
    await initialize(dut)
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / "protocols").is_dir())
    program = root / "protocols" / "v2_spi_mode0_a5.hex"
    words = [int(line.strip(), 16) for line in program.read_text().splitlines() if line.strip()]
    assert len(words) == 44

    for address, word in enumerate(words):
        await write_word(dut, address, word)

    await start_program(dut, pin_value=0)

    cycle = 0
    last_clk = None
    rising_cycles = []
    falling_cycles = []
    sampled_bits = []
    cs_released_cycle = None

    for _ in range(3000):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        cycle += 1

        oe = int(dut.uio_oe.value)
        out = int(dut.uio_out.value)

        if (oe & 0x07) == 0x07 and last_clk is None:
            last_clk = (out >> 2) & 1
        elif (oe & 0x07) == 0x07:
            clk_value = (out >> 2) & 1
            mosi_value = (out >> 1) & 1
            cs_value = out & 1

            if last_clk == 0 and clk_value == 1:
                assert cs_value == 0, "Chip select must remain active during transfer"
                rising_cycles.append(cycle)
                sampled_bits.append(mosi_value)
            elif last_clk == 1 and clk_value == 0:
                falling_cycles.append(cycle)

            last_clk = clk_value

            if cs_value == 1:
                cs_released_cycle = cycle
                break

    expected_bits = [1, 0, 1, 0, 0, 1, 0, 1]
    assert sampled_bits == expected_bits, f"SPI data bits: {sampled_bits}"
    assert len(rising_cycles) == 8, f"Expected 8 rising edges, got {len(rising_cycles)}"
    assert len(falling_cycles) == 8, f"Expected 8 falling edges, got {len(falling_cycles)}"
    assert all(f - r == 24 for r, f in zip(rising_cycles, falling_cycles)), f"SPI high times: {list(zip(rising_cycles, falling_cycles))}"
    assert all(rising_cycles[i + 1] - rising_cycles[i] == 50 for i in range(7)), f"SPI rising cycles: {rising_cycles}"
    assert cs_released_cycle is not None, "Chip select was never released"
    assert cs_released_cycle - falling_cycles[-1] == 2, "Chip select release timing mismatch"
    dut._log.info("PASS: SPI Mode 0 frame 0xA5, 8 clock pulses, timing and chip-select release verified")


@cocotb.test()
async def test_i2c_address_probe_ack_stop(dut):
    await initialize(dut)
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / "protocols").is_dir())
    program = root / "protocols" / "v2_i2c_address_probe.hex"
    words = [int(line.strip(), 16) for line in program.read_text().splitlines() if line.strip()]
    assert len(words) == 44

    for address, word in enumerate(words):
        await write_word(dut, address, word)

    await start_program(dut, pin_value=0xFF)

    cycle = 0
    previous_master_scl_low = False
    previous_bus_sda = 1
    previous_bus_scl = 1
    rising_count = 0
    address_bits = []
    ack_level = None
    slave_ack_active = False
    start_cycles = []
    stop_cycle = None

    for _ in range(5000):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        cycle += 1

        oe = int(dut.uio_oe.value)
        out = int(dut.uio_out.value)
        master_sda_low = bool((oe & 0x02) and not (out & 0x02))
        master_scl_low = bool((oe & 0x04) and not (out & 0x04))

        if previous_master_scl_low and not master_scl_low:
            rising_count += 1
            if rising_count == 9:
                slave_ack_active = True

        if master_scl_low and not previous_master_scl_low and rising_count >= 9:
            slave_ack_active = False

        bus_scl = 0 if master_scl_low else 1
        bus_sda = 0 if master_sda_low or slave_ack_active else 1

        if previous_bus_scl and bus_scl and previous_bus_sda and not bus_sda:
            start_cycles.append(cycle)
        if previous_bus_scl and bus_scl and not previous_bus_sda and bus_sda:
            stop_cycle = cycle if stop_cycle is None else stop_cycle

        if 1 <= rising_count <= 8 and previous_master_scl_low and not master_scl_low:
            address_bits.append(bus_sda)
        if rising_count == 9 and ack_level is None:
            ack_level = bus_sda

        bus_input = 0xFF
        if not bus_scl:
            bus_input &= ~0x04
        if not bus_sda:
            bus_input &= ~0x02
        dut.uio_in.value = bus_input

        previous_master_scl_low = master_scl_low
        previous_bus_scl = bus_scl
        previous_bus_sda = bus_sda

        if stop_cycle is not None and cycle >= stop_cycle + 10:
            break

    assert address_bits == [1, 0, 1, 0, 0, 0, 0, 0], f"Address bits: {address_bits}"
    assert ack_level == 0, f"Expected slave ACK low, got {ack_level}"
    assert len(start_cycles) == 1, f"START events: {start_cycles}"
    assert stop_cycle is not None, "I2C STOP condition not observed"
    assert rising_count == 10, f"Expected 9 transaction clocks plus STOP setup edge, got {rising_count}"
    assert int(dut.uio_oe.value) & 0x80 == 0, "NACK/fault path unexpectedly activated"
    assert int(dut.uio_oe.value) & 0x06 == 0, "SDA/SCL should be released after STOP"
    dut._log.info("PASS: I2C address 0x50 write probe, ACK, START and STOP verified")


@cocotb.test()
async def test_i2c_nack_releases_bus(dut):
    await initialize(dut)
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / "protocols").is_dir())
    program = root / "protocols" / "v2_i2c_address_probe.hex"
    words = [int(line.strip(), 16) for line in program.read_text().splitlines() if line.strip()]
    assert len(words) == 44

    for address, word in enumerate(words):
        await write_word(dut, address, word)

    await start_program(dut, pin_value=0xFF)
    released_after_nack = False

    for _ in range(5000):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        oe = int(dut.uio_oe.value)
        out = int(dut.uio_out.value)
        master_scl_low = bool((oe & 0x04) and not (out & 0x04))
        master_sda_low = bool((oe & 0x02) and not (out & 0x02))

        bus_input = 0xFF
        if master_scl_low:
            bus_input &= ~0x04
        if master_sda_low:
            bus_input &= ~0x02
        dut.uio_in.value = bus_input

        if (oe & 0x80) and (out & 0x80) and (oe & 0x06) == 0:
            released_after_nack = True
            break

    assert released_after_nack, "NACK did not signal failure and release SDA/SCL"
    assert int(dut.uio_oe.value) & 0x06 == 0
    assert int(dut.uio_out.value) & 0x80
    dut._log.info("PASS: I2C NACK signals failure and releases SDA/SCL")

@cocotb.test()
async def test_i2c_write_zero_byte(dut):
    await initialize(dut)
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / "protocols").is_dir())
    program = root / "protocols" / "v2_i2c_write_00.hex"
    words = [int(line.strip(), 16) for line in program.read_text().splitlines() if line.strip()]
    assert len(words) == 61

    for address, word in enumerate(words):
        await write_word(dut, address, word)

    await start_program(dut, pin_value=0xFF)

    cycle = 0
    previous_master_scl_low = False
    previous_bus_sda = 1
    previous_bus_scl = 1
    rising_count = 0
    address_bits = []
    data_bits = []
    ack_levels = {}
    slave_ack_active = False
    start_cycles = []
    stop_cycle = None

    for _ in range(6000):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        cycle += 1

        oe = int(dut.uio_oe.value)
        out = int(dut.uio_out.value)

        master_sda_low = bool((oe & 0x02) and not (out & 0x02))
        master_scl_low = bool((oe & 0x04) and not (out & 0x04))

        on_rising = previous_master_scl_low and not master_scl_low

        if on_rising:
            rising_count += 1
            if rising_count in (9, 18):
                slave_ack_active = True

        if master_scl_low and not previous_master_scl_low and rising_count in (9, 18):
            slave_ack_active = False

        bus_scl = 0 if master_scl_low else 1
        bus_sda = 0 if master_sda_low or slave_ack_active else 1

        if previous_bus_scl and bus_scl and previous_bus_sda and not bus_sda:
            start_cycles.append(cycle)

        if previous_bus_scl and bus_scl and not previous_bus_sda and bus_sda:
            stop_cycle = cycle if stop_cycle is None else stop_cycle

        if on_rising:
            if 1 <= rising_count <= 8:
                address_bits.append(bus_sda)
            elif 10 <= rising_count <= 17:
                data_bits.append(bus_sda)
            elif rising_count in (9, 18):
                ack_levels[rising_count] = bus_sda

        bus_input = 0xFF
        if not bus_scl:
            bus_input &= ~0x04
        if not bus_sda:
            bus_input &= ~0x02
        dut.uio_in.value = bus_input

        previous_master_scl_low = master_scl_low
        previous_bus_scl = bus_scl
        previous_bus_sda = bus_sda

        if stop_cycle is not None and cycle >= stop_cycle + 10:
            break

    assert address_bits == [1, 0, 1, 0, 0, 0, 0, 0], f"Address: {address_bits}"
    assert data_bits == [0] * 8, f"Data: {data_bits}"
    assert ack_levels == {9: 0, 18: 0}, f"ACK levels: {ack_levels}"
    assert len(start_cycles) == 1, f"START events: {start_cycles}"
    assert stop_cycle is not None, "STOP condition not observed"
    assert rising_count == 19, f"Expected 19 SCL rising edges, got {rising_count}"
    assert int(dut.uio_oe.value) & 0x80 == 0, "Unexpected I2C error marker"
    assert int(dut.uio_oe.value) & 0x06 == 0, "SDA/SCL not released after STOP"
    dut._log.info("PASS: I2C address 0x50, data 0x00, two ACKs and STOP")


async def run_i2c_program(dut, words, payload_count, ack_edges, limit=12000):
    for address, word in enumerate(words):
        await write_word(dut, address, word)
    await start_program(dut, pin_value=0xFF)

    ack_clock_indices = {9 + 9 * index for index in range(payload_count + 1)}
    ack_edges = set(ack_edges)
    previous_master_scl_low = False
    previous_bus_sda = 1
    previous_bus_scl = 1
    slave_ack_active = False
    rising_count = 0
    cycle = 0
    address_bits = []
    data_bits = [[] for _ in range(payload_count)]
    ack_levels = {}
    start_cycles = []
    stop_cycle = None
    error_seen = False

    for _ in range(limit):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        cycle += 1

        oe = int(dut.uio_oe.value)
        out = int(dut.uio_out.value)
        master_sda_low = bool((oe & 0x02) and not (out & 0x02))
        master_scl_low = bool((oe & 0x04) and not (out & 0x04))
        on_rising = previous_master_scl_low and not master_scl_low

        if on_rising:
            rising_count += 1
            if rising_count in ack_edges:
                slave_ack_active = True

        if master_scl_low and not previous_master_scl_low and rising_count in ack_clock_indices:
            slave_ack_active = False

        bus_scl = 0 if master_scl_low else 1
        bus_sda = 0 if master_sda_low or slave_ack_active else 1

        if previous_bus_scl and bus_scl and previous_bus_sda and not bus_sda:
            start_cycles.append(cycle)
        if previous_bus_scl and bus_scl and not previous_bus_sda and bus_sda:
            stop_cycle = cycle if stop_cycle is None else stop_cycle

        if on_rising:
            if 1 <= rising_count <= 8:
                address_bits.append(bus_sda)
            for index in range(payload_count):
                first_bit = 10 + index * 9
                if first_bit <= rising_count < first_bit + 8:
                    data_bits[index].append(bus_sda)
            if rising_count in ack_clock_indices:
                ack_levels[rising_count] = bus_sda

        bus_input = 0xFF
        if not bus_scl:
            bus_input &= ~0x04
        if not bus_sda:
            bus_input &= ~0x02
        dut.uio_in.value = bus_input

        previous_master_scl_low = master_scl_low
        previous_bus_scl = bus_scl
        previous_bus_sda = bus_sda

        if (oe & 0x80) and (out & 0x80) and (oe & 0x06) == 0:
            error_seen = True
            break
        if stop_cycle is not None and cycle >= stop_cycle + 10:
            break

    return {
        "address_bits": address_bits,
        "data_bits": data_bits,
        "ack_levels": ack_levels,
        "start_cycles": start_cycles,
        "stop_cycle": stop_cycle,
        "rising_count": rising_count,
        "error_seen": error_seen,
        "pin_oe": int(dut.uio_oe.value),
        "pin_out": int(dut.uio_out.value),
    }


@cocotb.test()
async def test_i2c_write_two_arbitrary_bytes(dut):
    await initialize(dut)
    _, words = build_program(0x50, [0xA5, 0x3C])
    assert len(words) == 56
    result = await run_i2c_program(dut, words, 2, {9, 18, 27})

    assert result["address_bits"] == [1, 0, 1, 0, 0, 0, 0, 0]
    assert result["data_bits"] == [
        [1, 0, 1, 0, 0, 1, 0, 1],
        [0, 0, 1, 1, 1, 1, 0, 0],
    ], f"Data bits: {result['data_bits']}"
    assert result["ack_levels"] == {9: 0, 18: 0, 27: 0}, f"ACK levels: {result['ack_levels']}"
    assert len(result["start_cycles"]) == 1, f"START events: {result['start_cycles']}"
    assert result["stop_cycle"] is not None, "STOP condition not observed"
    assert result["rising_count"] == 28, f"Expected 28 SCL rising edges, got {result['rising_count']}"
    assert not result["error_seen"]
    assert result["pin_oe"] & 0x80 == 0
    assert result["pin_oe"] & 0x06 == 0
    dut._log.info("PASS: I2C address 0x50, data bytes 0xA5 and 0x3C, three ACKs and STOP")


@cocotb.test()
async def test_i2c_write_nack_on_second_byte(dut):
    await initialize(dut)
    _, words = build_program(0x50, [0xA5, 0x3C])
    result = await run_i2c_program(dut, words, 2, {9})

    assert result["address_bits"] == [1, 0, 1, 0, 0, 0, 0, 0]
    assert result["data_bits"][0] == [1, 0, 1, 0, 0, 1, 0, 1]
    assert result["ack_levels"].get(9) == 0
    assert result["ack_levels"].get(18) == 1
    assert result["error_seen"], "NACK on data byte did not raise the error marker"
    assert result["pin_oe"] & 0x80
    assert result["pin_oe"] & 0x06 == 0
    dut._log.info("PASS: I2C data-byte NACK raises error marker and releases SDA/SCL")


async def run_spi_mode_tx(dut, mode, data=0xA5):
    await initialize(dut)
    _, words = build_spi_program(mode, data)
    assert len(words) == 11
    for address, word in enumerate(words):
        await write_word(dut, address, word)
    await start_program(dut)

    cpol = (mode >> 1) & 1
    cpha = mode & 1
    expected_bits = [(data >> bit) & 1 for bit in range(7, -1, -1)]
    previous_clock = None
    initial_clock = None
    leading_cycles = []
    trailing_cycles = []
    sampled_bits = []
    final_clock = None
    cs_deasserted = False

    for cycle in range(2500):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        oe = int(dut.uio_oe.value)
        out = int(dut.uio_out.value)
        cs_enabled = bool(oe & 0x01)
        cs_high = bool(out & 0x01)
        clock_enabled = bool(oe & 0x04)
        clock_value = (out >> 2) & 1

        if cs_enabled and clock_enabled and not cs_high:
            if initial_clock is None:
                initial_clock = clock_value
            elif clock_value != previous_clock:
                if previous_clock == cpol and clock_value == 1 - cpol:
                    leading_cycles.append(cycle)
                    if cpha == 0:
                        assert oe & 0x02, "MOSI must be actively driven at CPHA=0 sample edge"
                        sampled_bits.append((out >> 1) & 1)
                elif previous_clock == 1 - cpol and clock_value == cpol:
                    trailing_cycles.append(cycle)
                    if cpha == 1:
                        assert oe & 0x02, "MOSI must be actively driven at CPHA=1 sample edge"
                        sampled_bits.append((out >> 1) & 1)
            previous_clock = clock_value

        if cs_enabled and cs_high:
            final_clock = clock_value
            cs_deasserted = True
            break

    assert initial_clock == cpol, f"Mode {mode}: idle clock should be {cpol}, got {initial_clock}"
    assert len(leading_cycles) == 8, f"Mode {mode}: expected 8 leading edges, got {leading_cycles}"
    assert len(trailing_cycles) == 8, f"Mode {mode}: expected 8 trailing edges, got {trailing_cycles}"
    assert sampled_bits == expected_bits, f"Mode {mode}: expected {expected_bits}, got {sampled_bits}"
    assert cs_deasserted, f"Mode {mode}: chip select was never deasserted"
    assert final_clock == cpol, f"Mode {mode}: clock did not return to idle polarity"
    assert len(set(b - a for a, b in zip(leading_cycles, leading_cycles[1:]))) == 1
    assert len(set(b - a for a, b in zip(trailing_cycles, trailing_cycles[1:]))) == 1
    dut._log.info(f"PASS: SPI Mode {mode} transmitted 0x{data:02X}, 8 sample edges, correct CPOL/CPHA")


@cocotb.test()
async def test_spi_mode1_a5_waveform(dut):
    await run_spi_mode_tx(dut, 1, 0xA5)


@cocotb.test()
async def test_spi_mode2_a5_waveform(dut):
    await run_spi_mode_tx(dut, 2, 0xA5)


@cocotb.test()
async def test_spi_mode3_a5_waveform(dut):
    await run_spi_mode_tx(dut, 3, 0xA5)


@cocotb.test()
async def test_reprogram_reset_and_output_gating(dut):
    await initialize(dut)

    await write_word(dut, 0, 0x1001)
    await write_word(dut, 1, 0x0000)
    await start_program(dut)

    await ClockCycles(dut.clk, 2)
    await Timer(1, unit="ns")

    assert int(dut.uio_oe.value) == 0x01
    assert int(dut.uio_out.value) & 0x01

    dut.ena.value = 0
    await Timer(1, unit="ns")

    assert int(dut.uio_oe.value) == 0

    dut.ena.value = 1
    await Timer(1, unit="ns")

    assert int(dut.uio_oe.value) == 0x01

    dut.ui_in.value = 0x80
    await Timer(1, unit="ns")

    assert int(dut.uio_oe.value) == 0

    await write_word(dut, 0, 0x1201)
    await write_word(dut, 1, 0x0000)
    await start_program(dut)

    await ClockCycles(dut.clk, 2)
    await Timer(1, unit="ns")

    assert int(dut.uio_oe.value) == 0x04
    assert int(dut.uio_out.value) & 0x04

    dut.rst_n.value = 0
    await Timer(1, unit="ns")

    assert int(dut.uio_oe.value) == 0

    await ClockCycles(dut.clk, 2)
    await Timer(1, unit="ns")

    dut.rst_n.value = 1

    await ClockCycles(dut.clk, 2)
    await Timer(1, unit="ns")

    assert int(dut.uio_oe.value) == 0x04
    assert int(dut.uio_out.value) & 0x04


@cocotb.test()
async def test_morph_x_capture_timestamp_and_readback(dut):
    await initialize(dut)
    await write_word(dut, 0, 0x0000)
    await start_program(dut, pin_value=0x00)
    await ClockCycles(dut.clk, 6)
    await Timer(1, unit="ns")

    dut.uio_in.value = 0x01
    await ClockCycles(dut.clk, 5)
    await Timer(1, unit="ns")
    dut.uio_in.value = 0x03
    await ClockCycles(dut.clk, 5)
    await Timer(1, unit="ns")

    dut.ui_in.value = 0x60
    await Timer(1, unit="ns")
    status = int(dut.uo_out.value)
    assert status & 0x0F == 2, f"Expected two edges, status=0x{status:02X}"
    assert status & 0x10 == 0

    def select(slot, page):
        return 0x40 | (page << 3) | slot

    values = []
    for slot in (0, 1):
        record = []
        for page in range(4):
            dut.ui_in.value = select(slot, page)
            await Timer(1, unit="ns")
            record.append(int(dut.uo_out.value))
        values.append(record)
    assert values[0][:2] == [0x01, 0x01], f"First event: {values[0]}"
    assert values[1][:2] == [0x03, 0x02], f"Second event: {values[1]}"
    first_time = values[0][2] | (values[0][3] << 8)
    second_time = values[1][2] | (values[1][3] << 8)
    assert 0 < (second_time - first_time) & 0xFFFF <= 6
    assert int(dut.uio_oe.value) == 0


@cocotb.test()
async def test_morph_x_trace_overflow_and_reset(dut):
    await initialize(dut)
    await write_word(dut, 0, 0x0000)
    await start_program(dut, pin_value=0x00)
    await ClockCycles(dut.clk, 6)
    await Timer(1, unit="ns")

    for n in range(9):
        dut.uio_in.value = (n + 1) & 1
        await ClockCycles(dut.clk, 5)
        await Timer(1, unit="ns")

    dut.ui_in.value = 0x60
    await Timer(1, unit="ns")
    status = int(dut.uo_out.value)
    assert status & 0x0F == 8, f"Count did not saturate: {status:02X}"
    assert status & 0x20, "Full bit missing"
    assert status & 0x10, "Overflow bit missing"

    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    await Timer(1, unit="ns")
    status = int(dut.uo_out.value)
    assert status & 0x3F == 0, f"Reset did not clear trace: {status:02X}"

# MORPH X M3: true top-level pin capture -> readback -> compiler -> replay.
# MORPH_X_E2E_V04_BEGIN
async def morph_x_e2e_roundtrip(dut, pin, with_noise):
    from morph_x_host import read_capture_async
    from morph_x_replay import capture_to_ir, compile_and_verify
    from morph_x_trace import decode_capture

    await initialize(dut)
    await write_word(dut, 0, 0x0000)  # HALT while capturing; no protocol pins driven
    await start_program(dut, pin_value=0)
    await ClockCycles(dut.clk, 6)
    await Timer(1, unit="ns")

    selected = 1 << pin
    other = 1 << ((pin + 3) % 8)
    if with_noise:
        # An unrelated input transition between selected-pin transitions:
        # pin timeline: high@0, low@6, high@12.
        stimulus = [(0, selected), (4, selected | other),
                    (6, other), (12, selected | other)]
    else:
        stimulus = [(0, selected), (6, 0), (12, selected)]

    prev = 0
    for tick, level in stimulus:
        if tick > prev:
            await ClockCycles(dut.clk, tick - prev)
            await Timer(1, unit="ns")
        dut.uio_in.value = level
        await Timer(1, unit="ns")
        prev = tick

    # Two synchronizer stages plus record bookkeeping must settle.
    await ClockCycles(dut.clk, 6)
    await Timer(1, unit="ns")

    async def read_register(ui_value):
        dut.ui_in.value = ui_value
        await Timer(1, unit="ns")
        return int(dut.uo_out.value)

    frame = await read_capture_async(read_register)
    decoded = decode_capture(frame)
    assert decoded["count"] == len(stimulus), (
        f"capture missed events: {decoded!r}"
    )
    assert not decoded["overflow"], "Unexpected capture overflow"
    assert [e["changed"] for e in decoded["events"]] == [
        selected if (a == 0 or not with_noise or a >= 2) else other
        for a in range(len(stimulus))
    ], "capture event pin masks do not match physical input changes"

    ir = capture_to_ir(frame, pin)
    expected = [
        {"cycle": 0, "value": 1},
        {"cycle": 6, "value": 0},
        {"cycle": 12, "value": 1},
    ]
    assert ir["events"] == expected, f"captured schedule: {ir['events']!r}"
    generated = compile_and_verify(ir)
    words = [int(line, 16) for line in generated["hex"].splitlines()]
    assert len(words) <= 64
    assert generated["report"]["verification"]["model_verified"] is True
    assert not int(dut.uio_oe.value), "Capture-only HALT should not drive pins"

    # Real chip loader: assert ui_in[7] and load each 16-bit instruction in
    # the same two byte writes used by the existing 24 Cocotb tests.
    for address, word in enumerate(words):
        await write_word(dut, address, word)
    await start_program(dut, pin_value=0)

    observed = []
    previous_level = None
    released = False
    for tick in range(160):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        oe = int(dut.uio_oe.value)
        value = int(dut.uio_out.value)
        assert oe & ~selected == 0, f"unexpected enabled pin(s): 0x{oe:02X}"
        if oe & selected:
            level = 1 if value & selected else 0
            if previous_level is None or level != previous_level:
                observed.append({"cycle": tick, "value": level})
                previous_level = level
        elif observed:
            released = True
            break

    assert released, "replay did not release its output pin"
    relative = [
        {"cycle": e["cycle"] - observed[0]["cycle"], "value": e["value"]}
        for e in observed
    ]
    assert relative == expected, f"top-level replay mismatch: {relative!r}"
    await ClockCycles(dut.clk, 6)
    await Timer(1, unit="ns")
    assert int(dut.uio_oe.value) == 0, "pins re-enabled after release"
    dut._log.info(
        "MORPH X TOP E2E PASS pin=%d noisy=%s captured=%d words=%d transitions=%s",
        pin, with_noise, decoded["count"], len(words), relative,
    )


@cocotb.test()
async def test_morph_x_end_to_end_pin0(dut):
    await morph_x_e2e_roundtrip(dut, pin=0, with_noise=False)


@cocotb.test()
async def test_morph_x_end_to_end_pin5_background_traffic(dut):
    await morph_x_e2e_roundtrip(dut, pin=5, with_noise=True)
# MORPH_X_E2E_V04_END
