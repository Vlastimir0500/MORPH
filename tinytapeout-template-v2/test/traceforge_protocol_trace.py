import hashlib
import json
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer, RisingEdge

ROOT = Path(__file__).resolve().parents[2]
TRACE_DIR = ROOT / "traceforge" / "rtl_run" / "protocol_traces"
TRACE_DIR.mkdir(parents=True, exist_ok=True)

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

def load_program(relative_path):
    path = ROOT / relative_path
    words = [int(line.strip(), 16) for line in path.read_text().splitlines() if line.strip()]
    return words

def save_trace(filename, protocol, case_name, samples):
    rtl_path = ROOT / "rtl" / "morph_engine_v2.sv"
    data = {
        "schema": "morph.protocol-trace.v0.1",
        "protocol": protocol,
        "case": case_name,
        "source_module": "traceforge_protocol_trace.py",
        "rtl_sha256": hashlib.sha256(rtl_path.read_bytes()).hexdigest(),
        "sample_count": len(samples),
        "samples": samples,
    }
    (TRACE_DIR / filename).write_text(json.dumps(data, indent=2) + "\n")

@cocotb.test()
async def test_spi_mode0_a5_trace(dut):
    await initialize(dut)
    words = load_program("protocols/v2_spi_mode0_a5.hex")
    assert len(words) == 44
    for address, word in enumerate(words):
        await write_word(dut, address, word)
    await start_program(dut, pin_value=0)
    samples = []
    cycle = 0
    saw_cs_active = False
    saw_cs_release = False
    for _ in range(3000):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        cycle += 1
        oe = int(dut.uio_oe.value)
        out = int(dut.uio_out.value)
        samples.append({
            "cycle": cycle,
            "uio_oe": oe,
            "uio_out": out,
            "uio_in": int(dut.uio_in.value),
            "uo_out": int(dut.uo_out.value),
        })
        if (oe & 0x07) == 0x07 and (out & 0x01) == 0:
            saw_cs_active = True
        elif saw_cs_active and (oe & 0x07) == 0x07 and (out & 0x01) != 0:
            saw_cs_release = True
            break
    assert saw_cs_active and saw_cs_release, "SPI trace did not capture an active and released chip select"
    save_trace("spi_mode0_a5_trace.json", "SPI Mode 0", "A5 single-byte transfer", samples)
    dut._log.info("TRACEFORGE: SPI Mode 0 trace recorded: %d samples", len(samples))

@cocotb.test()
async def test_i2c_address_probe_ack_trace(dut):
    await initialize(dut)
    words = load_program("protocols/v2_i2c_address_probe.hex")
    assert len(words) == 44
    for address, word in enumerate(words):
        await write_word(dut, address, word)
    await start_program(dut, pin_value=0xFF)
    samples = []
    cycle = 0
    previous_master_scl_low = False
    previous_bus_sda = 1
    previous_bus_scl = 1
    rising_count = 0
    slave_ack_active = False
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
            pass
        if previous_bus_scl and bus_scl and not previous_bus_sda and bus_sda and stop_cycle is None:
            stop_cycle = cycle
        bus_input = 0xFF
        if not bus_scl:
            bus_input &= ~0x04
        if not bus_sda:
            bus_input &= ~0x02
        samples.append({
            "cycle": cycle,
            "uio_oe": oe,
            "uio_out": out,
            "uio_in_before_update": int(dut.uio_in.value),
            "uio_in_next": bus_input,
            "master_sda_low": master_sda_low,
            "master_scl_low": master_scl_low,
            "slave_sda_low": slave_ack_active,
            "bus_sda": bus_sda,
            "bus_scl": bus_scl,
            "rising_count_fixture": rising_count,
            "uo_out": int(dut.uo_out.value),
        })
        dut.uio_in.value = bus_input
        previous_master_scl_low = master_scl_low
        previous_bus_scl = bus_scl
        previous_bus_sda = bus_sda
        if stop_cycle is not None and cycle >= stop_cycle + 10:
            break
    assert stop_cycle is not None, "I2C ACK trace did not reach a STOP condition"
    save_trace("i2c_address_probe_ack_trace.json", "I2C", "0x50 write address with simulated ACK", samples)
    dut._log.info("TRACEFORGE: I2C ACK trace recorded: %d samples", len(samples))

@cocotb.test()
async def test_i2c_nack_trace(dut):
    await initialize(dut)
    words = load_program("protocols/v2_i2c_address_probe.hex")
    assert len(words) == 44
    for address, word in enumerate(words):
        await write_word(dut, address, word)
    await start_program(dut, pin_value=0xFF)
    samples = []
    cycle = 0
    released_after_nack = False
    for _ in range(5000):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        cycle += 1
        oe = int(dut.uio_oe.value)
        out = int(dut.uio_out.value)
        master_scl_low = bool((oe & 0x04) and not (out & 0x04))
        master_sda_low = bool((oe & 0x02) and not (out & 0x02))
        bus_input = 0xFF
        if master_scl_low:
            bus_input &= ~0x04
        if master_sda_low:
            bus_input &= ~0x02
        samples.append({
            "cycle": cycle,
            "uio_oe": oe,
            "uio_out": out,
            "uio_in_before_update": int(dut.uio_in.value),
            "uio_in_next": bus_input,
            "master_sda_low": master_sda_low,
            "master_scl_low": master_scl_low,
            "slave_sda_low": False,
            "bus_sda": 0 if master_sda_low else 1,
            "bus_scl": 0 if master_scl_low else 1,
            "uo_out": int(dut.uo_out.value),
        })
        dut.uio_in.value = bus_input
        if (oe & 0x80) and (out & 0x80) and (oe & 0x06) == 0:
            released_after_nack = True
            break
    assert released_after_nack, "I2C NACK trace did not reach fault plus released SDA/SCL"
    save_trace("i2c_nack_trace.json", "I2C", "no-slave-ACK NACK handling", samples)
    dut._log.info("TRACEFORGE: I2C NACK trace recorded: %d samples", len(samples))
