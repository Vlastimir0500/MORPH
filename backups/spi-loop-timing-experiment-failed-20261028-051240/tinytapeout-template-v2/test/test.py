import cocotb
from pathlib import Path
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer, RisingEdge


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


@cocotb.test()
async def test_uart_tx_a5_waveform(dut):
    await initialize(dut)
    root = Path(__file__).resolve().parents[2]
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
    root = Path(__file__).resolve().parents[2]
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
    root = Path(__file__).resolve().parents[2]
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
    root = Path(__file__).resolve().parents[2]
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
    root = Path(__file__).resolve().parents[2]
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
    root = Path(__file__).resolve().parents[2]
    program = root / "protocols" / "v2_spi_mode0_a5.hex"
    words = [int(line.strip(), 16) for line in program.read_text().splitlines() if line.strip()]
    assert len(words) == 41

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
    root = Path(__file__).resolve().parents[2]
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
    root = Path(__file__).resolve().parents[2]
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
