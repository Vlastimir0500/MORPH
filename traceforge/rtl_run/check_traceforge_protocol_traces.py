import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE_DIR = ROOT / "traceforge" / "rtl_run" / "protocol_traces"
REPORT_DIR = ROOT / "traceforge" / "reports"
CONTRACT_DIR = ROOT / "traceforge" / "contracts"
RESULTS_XML = REPORT_DIR / "traceforge_protocol_trace_results.xml"

checks = []
def check(name, passed, observed, expected):
    checks.append({"name": name, "status": "PASS" if passed else "FAIL", "observed": observed, "expected": expected})

def read_json(path):
    return json.loads(path.read_text())

def signal(sample, name):
    return int(sample[name])

def trace_sample_sha(trace):
    return trace.get("rtl_sha256")

spi_contract = read_json(CONTRACT_DIR / "spi_trace_contract_v0.1.json")
i2c_contract = read_json(CONTRACT_DIR / "i2c_trace_contract_v0.1.json")
spi = read_json(TRACE_DIR / spi_contract["trace_file"])
i2c_ack = read_json(TRACE_DIR / i2c_contract["ack_trace_file"])
i2c_nack = read_json(TRACE_DIR / i2c_contract["nack_trace_file"])

check("SPI trace schema", spi.get("schema") == "morph.protocol-trace.v0.1", spi.get("schema"), "morph.protocol-trace.v0.1")
check("I2C ACK trace schema", i2c_ack.get("schema") == "morph.protocol-trace.v0.1", i2c_ack.get("schema"), "morph.protocol-trace.v0.1")
check("I2C NACK trace schema", i2c_nack.get("schema") == "morph.protocol-trace.v0.1", i2c_nack.get("schema"), "morph.protocol-trace.v0.1")

spi_req = spi_contract["requirements"]
spi_samples = spi["samples"]
spi_rising = []
spi_falling = []
spi_bits = []
last_clk = None
saw_cs_active = False
cs_release_cycle = None
active_cycle_out = {}
for sample in spi_samples:
    oe = signal(sample, "uio_oe")
    out = signal(sample, "uio_out")
    cycle = int(sample["cycle"])
    if (oe & 0x07) != 0x07:
        continue
    cs_n = out & 0x01
    sclk = (out >> 2) & 1
    mosi = (out >> 1) & 1
    active_cycle_out[cycle] = out
    if cs_n == 0:
        saw_cs_active = True
    elif saw_cs_active and cs_release_cycle is None:
        cs_release_cycle = cycle
    if last_clk is None:
        last_clk = sclk
    elif last_clk == 0 and sclk == 1:
        spi_rising.append(cycle)
        spi_bits.append(mosi)
    elif last_clk == 1 and sclk == 0:
        spi_falling.append(cycle)
    last_clk = sclk

check("SPI captured active-low CS and release", saw_cs_active and cs_release_cycle is not None, {"active_seen": saw_cs_active, "release_cycle": cs_release_cycle}, "CS active and subsequently released")
check("SPI MOSI sequence", spi_bits == spi_req["mosi_bits"], spi_bits, spi_req["mosi_bits"])
check("SPI rising edge count", len(spi_rising) == spi_req["rising_edges"], len(spi_rising), spi_req["rising_edges"])
check("SPI falling edge count", len(spi_falling) == spi_req["falling_edges"], len(spi_falling), spi_req["falling_edges"])
spi_high = [f - r for r, f in zip(spi_rising, spi_falling)]
check("SPI high-phase durations", len(spi_high) == spi_req["rising_edges"] and all(v == spi_req["sclk_high_cycles"] for v in spi_high), spi_high, [spi_req["sclk_high_cycles"]] * spi_req["rising_edges"])
spi_spacing = [spi_rising[i + 1] - spi_rising[i] for i in range(len(spi_rising) - 1)]
check("SPI rising-edge spacing", len(spi_spacing) == spi_req["rising_edges"] - 1 and all(v == spi_req["rising_edge_spacing_cycles"] for v in spi_spacing), spi_spacing, [spi_req["rising_edge_spacing_cycles"]] * (spi_req["rising_edges"] - 1))
cs_during_edges = [((active_cycle_out.get(cycle, 1) & 0x01) == 0) for cycle in spi_rising]
check("SPI CS stays active at every rising edge", all(cs_during_edges), cs_during_edges, [True] * spi_req["rising_edges"])
cs_delta = None if cs_release_cycle is None or not spi_falling else cs_release_cycle - spi_falling[-1]
check("SPI CS release timing", cs_delta == spi_req["cs_release_after_final_falling_edge_cycles"], cs_delta, spi_req["cs_release_after_final_falling_edge_cycles"])


def analyze_i2c_ack(samples, requirements):
    previous_master_scl_low = False
    previous_bus_scl = 1
    previous_bus_sda = 1
    rising_count = 0
    address_bits = []
    ack_level = None
    start_cycles = []
    stop_cycles = []
    bus_model_consistent = True
    for sample in samples:
        oe = signal(sample, "uio_oe")
        out = signal(sample, "uio_out")
        master_sda_low = bool((oe & 0x02) and not (out & 0x02))
        master_scl_low = bool((oe & 0x04) and not (out & 0x04))
        if previous_master_scl_low and not master_scl_low:
            rising_count += 1
        slave_sda_low = bool(sample["slave_sda_low"])
        bus_scl = 0 if master_scl_low else 1
        bus_sda = 0 if master_sda_low or slave_sda_low else 1
        bus_model_consistent = bus_model_consistent and bus_scl == int(sample["bus_scl"]) and bus_sda == int(sample["bus_sda"])
        if previous_bus_scl and bus_scl and previous_bus_sda and not bus_sda:
            start_cycles.append(int(sample["cycle"]))
        if previous_bus_scl and bus_scl and not previous_bus_sda and bus_sda:
            stop_cycles.append(int(sample["cycle"]))
        if previous_master_scl_low and not master_scl_low and 1 <= rising_count <= 8:
            address_bits.append(bus_sda)
        if rising_count == 9 and ack_level is None:
            ack_level = bus_sda
        previous_master_scl_low = master_scl_low
        previous_bus_scl = bus_scl
        previous_bus_sda = bus_sda
    last = samples[-1] if samples else {}
    final_oe = int(last.get("uio_oe", 0))
    final_out = int(last.get("uio_out", 0))
    return {
        "address_bits": address_bits,
        "ack_level": ack_level,
        "start_cycles": start_cycles,
        "stop_cycles": stop_cycles,
        "master_scl_rising_edges": rising_count,
        "bus_model_consistent": bus_model_consistent,
        "final_uio_oe": final_oe,
        "final_uio_out": final_out,
        "final_lines_released": (final_oe & requirements["released_line_mask"]) == 0,
        "final_fault_clear": (final_oe & requirements["fault_mask"]) == 0,
    }

i2c_req = i2c_contract["requirements"]
i2c_ack_result = analyze_i2c_ack(i2c_ack["samples"], i2c_req)
check("I2C ACK trace bus reconstruction", i2c_ack_result["bus_model_consistent"], i2c_ack_result["bus_model_consistent"], True)
check("I2C address bits", i2c_ack_result["address_bits"] == i2c_req["address_bits"], i2c_ack_result["address_bits"], i2c_req["address_bits"])
check("I2C slave ACK level", i2c_ack_result["ack_level"] == i2c_req["ack_level"], i2c_ack_result["ack_level"], i2c_req["ack_level"])
check("I2C START count", len(i2c_ack_result["start_cycles"]) == i2c_req["start_count"], len(i2c_ack_result["start_cycles"]), i2c_req["start_count"])
check("I2C STOP observed", bool(i2c_ack_result["stop_cycles"]) if i2c_req["stop_required"] else True, i2c_ack_result["stop_cycles"], "at least one STOP" if i2c_req["stop_required"] else "not required")
check("I2C master clock-edge count", i2c_ack_result["master_scl_rising_edges"] == i2c_req["master_scl_rising_edges_including_stop_setup"], i2c_ack_result["master_scl_rising_edges"], i2c_req["master_scl_rising_edges_including_stop_setup"])
check("I2C no false fault after ACK", i2c_ack_result["final_fault_clear"], i2c_ack_result["final_uio_oe"] & i2c_req["fault_mask"], 0)
check("I2C lines released after STOP", i2c_ack_result["final_lines_released"], i2c_ack_result["final_uio_oe"] & i2c_req["released_line_mask"], 0)

nack_samples = i2c_nack["samples"]
nack_terminal = None
for sample in nack_samples:
    oe = signal(sample, "uio_oe")
    out = signal(sample, "uio_out")
    if (oe & i2c_req["fault_mask"]) and (out & i2c_req["fault_output_value"]) and (oe & i2c_req["released_line_mask"]) == 0:
        nack_terminal = sample
        break
check("I2C NACK fault is signaled", nack_terminal is not None, None if nack_terminal is None else {"cycle": nack_terminal["cycle"], "uio_oe": nack_terminal["uio_oe"], "uio_out": nack_terminal["uio_out"]}, "fault output asserted")
check("I2C NACK releases SDA/SCL", nack_terminal is not None and (int(nack_terminal["uio_oe"]) & i2c_req["released_line_mask"]) == 0, None if nack_terminal is None else int(nack_terminal["uio_oe"]) & i2c_req["released_line_mask"], 0)
check("I2C NACK trace contains no slave ACK", all(not bool(s.get("slave_sda_low", False)) for s in nack_samples), any(bool(s.get("slave_sda_low", False)) for s in nack_samples), False)

xml_cases = {}
xml_failures = []
if RESULTS_XML.exists():
    root_xml = ET.parse(RESULTS_XML).getroot()
    for case in root_xml.findall(".//testcase"):
        name = case.attrib.get("name", "").split(".")[-1]
        if case.find("failure") is not None or case.find("error") is not None:
            status = "FAIL"
            xml_failures.append(name)
        elif case.find("skipped") is not None:
            status = "SKIP"
        else:
            status = "PASS"
        xml_cases[name] = status
else:
    xml_failures.append("results XML missing")
required_cases = ["test_spi_mode0_a5_trace", "test_i2c_address_probe_ack_trace", "test_i2c_nack_trace"]
check("Fresh Cocotb trace tests passed", all(xml_cases.get(name) == "PASS" for name in required_cases) and not xml_failures, xml_cases, {name: "PASS" for name in required_cases})
check("Fresh Cocotb suite contains no failures", not xml_failures, xml_failures, [])

rtl = ROOT / "rtl" / "morph_engine_v2.sv"
engine_copy = ROOT / "tinytapeout-template-v2" / "src" / "morph_engine.sv"
def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
rtl_hash = sha256(rtl)
copy_hash = sha256(engine_copy)
before_hash = os.environ.get("MORPH_RTL_SHA256_BEFORE", "")
after_hash = os.environ.get("MORPH_RTL_SHA256_AFTER", "")
check("TinyTapeout engine matches production RTL", rtl_hash == copy_hash, {"production": rtl_hash, "tinytapeout_copy": copy_hash}, "identical SHA-256")
check("Production RTL unchanged by trace workflow", bool(before_hash) and before_hash == after_hash == rtl_hash, {"before": before_hash, "after": after_hash, "current": rtl_hash}, "same SHA-256 before and after")

passed = sum(item["status"] == "PASS" for item in checks)
failed = len(checks) - passed
result = {
    "schema": "morph.trace-validation-report.v0.1",
    "status": "PASS" if failed == 0 else "FAIL",
    "checks_passed": passed,
    "checks_failed": failed,
    "checks": checks,
    "cocotb_results": xml_cases,
    "rtl_sha256_before": before_hash,
    "rtl_sha256_after": after_hash,
    "rtl_sha256_current": rtl_hash,
    "tinytapeout_engine_sha256": copy_hash,
    "trace_files": [
        str(TRACE_DIR / spi_contract["trace_file"]),
        str(TRACE_DIR / i2c_contract["ack_trace_file"]),
        str(TRACE_DIR / i2c_contract["nack_trace_file"]),
    ],
    "spi_observations": {
        "samples": len(spi_samples),
        "mosi_bits": spi_bits,
        "rising_cycles": spi_rising,
        "falling_cycles": spi_falling,
        "high_phase_cycles": spi_high,
        "rising_edge_spacing_cycles": spi_spacing,
        "cs_release_cycle": cs_release_cycle,
    },
    "i2c_ack_observations": i2c_ack_result,
    "i2c_nack_observations": {
        "samples": len(nack_samples),
        "terminal_fault_release_cycle": None if nack_terminal is None else nack_terminal["cycle"],
    },
}
json_path = REPORT_DIR / "protocol_trace_contract_validation_v0.1.json"
md_path = REPORT_DIR / "protocol_trace_contract_validation_v0.1.md"
json_path.write_text(json.dumps(result, indent=2) + "\n")
lines = [
    "# MORPH Protocol Trace Contract Validation v0.1",
    "",
    f"**Status:** {result['status']}",
    f"**Checks:** {passed}/{len(checks)} passed",
    "",
    "## Independent trace checks",
    "",
    "| Check | Status | Observed | Expected |",
    "|---|---|---|---|",
]
for item in checks:
    observed = json.dumps(item["observed"], separators=(",", ":"))
    expected = json.dumps(item["expected"], separators=(",", ":"))
    lines.append(f"| {item['name']} | {item['status']} | `{observed}` | `{expected}` |")
lines += [
    "",
    "## Trace artifacts",
    "",
    f"- SPI Mode 0 A5: `{spi_contract['trace_file']}` ({len(spi_samples)} samples)",
    f"- I2C address probe ACK/STOP: `{i2c_contract['ack_trace_file']}` ({len(i2c_ack['samples'])} samples)",
    f"- I2C NACK and bus release: `{i2c_contract['nack_trace_file']}` ({len(nack_samples)} samples)",
    "",
    "## Reproducibility and scope",
    "",
    f"- Production RTL SHA-256 before run: `{before_hash}`",
    f"- Production RTL SHA-256 after run: `{after_hash}`",
    f"- TinyTapeout engine source matches production RTL: `{rtl_hash == copy_hash}`",
    "- The traces come from a fresh Cocotb simulation against the TinyTapeout V2 RTL wrapper.",
    "- The I2C slave ACK is a simulation stimulus; these results validate the address-probe sequence and ACK/NACK handling, not a full I2C controller.",
    "- This is RTL simulation evidence, not fabricated-silicon measurement.",
    "",
]
md_path.write_text("\n".join(lines))
print(json.dumps({"status": result["status"], "checks_passed": passed, "checks_failed": failed, "json_report": str(json_path), "markdown_report": str(md_path)}, indent=2))
for item in checks:
    print(f"{item['status']}: {item['name']}")
if failed:
    sys.exit(1)
