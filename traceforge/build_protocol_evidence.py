import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_XML = ROOT / "traceforge" / "rtl_run" / "tt_v2_protocol_results.xml"
REPORTS = ROOT / "traceforge" / "reports"

REQUIREMENTS = {
    "test_spi_mode0_a5_waveform": {
        "protocol": "spi",
        "program": "protocols/v2_spi_mode0_a5.morph",
        "hex": "protocols/v2_spi_mode0_a5.hex",
        "markers": [
            "expected_bits = [1, 0, 1, 0, 0, 1, 0, 1]",
            "assert len(rising_cycles) == 8",
            "assert len(falling_cycles) == 8",
            "f - r == 24",
            "rising_cycles[i + 1] - rising_cycles[i] == 50",
            "cs_released_cycle - falling_cycles[-1] == 2",
        ],
        "requirements": {
            "expected_data_bits": [1, 0, 1, 0, 0, 1, 0, 1],
            "rising_edges": 8,
            "falling_edges": 8,
            "high_time_cycles": 24,
            "rising_period_cycles": 50,
            "cs_release_delay_cycles": 2,
        },
    },
    "test_i2c_address_probe_ack_stop": {
        "protocol": "i2c",
        "program": "protocols/v2_i2c_address_probe.morph",
        "hex": "protocols/v2_i2c_address_probe.hex",
        "markers": [
            "address_bits == [1, 0, 1, 0, 0, 0, 0, 0]",
            "ack_level == 0",
            "len(start_cycles) == 1",
            "stop_cycle is not None",
            "rising_count == 10",
            "int(dut.uio_oe.value) & 0x80 == 0",
            "int(dut.uio_oe.value) & 0x06 == 0",
        ],
        "requirements": {
            "address_bits": [1, 0, 1, 0, 0, 0, 0, 0],
            "ack_level": 0,
            "start_events": 1,
            "stop_condition_required": True,
            "rising_count": 10,
            "nack_flag_expected": False,
            "bus_lines_released_after_stop": True,
        },
    },
    "test_i2c_nack_releases_bus": {
        "protocol": "i2c",
        "program": "protocols/v2_i2c_address_probe.morph",
        "hex": "protocols/v2_i2c_address_probe.hex",
        "markers": [
            "assert released_after_nack",
            "int(dut.uio_oe.value) & 0x06 == 0",
            "int(dut.uio_out.value) & 0x80",
        ],
        "requirements": {
            "nack_flag_expected": True,
            "sda_scl_released_after_nack": True,
        },
    },
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_test_functions(text):
    pattern = re.compile(
        r"(?m)^@cocotb\.test\(\)\s*\nasync def (\w+)\(dut\):"
    )
    found = list(pattern.finditer(text))
    functions = {}
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else len(text)
        functions[match.group(1)] = text[match.end():end]
    return functions


def main():
    if not RESULTS_XML.is_file():
        raise SystemExit(f"Missing fresh test results: {RESULTS_XML}")

    test_path = ROOT / "tinytapeout-template-v2/test/test.py"
    wrapper_path = ROOT / "tinytapeout-template-v2/src/project.v"
    tt_engine_path = ROOT / "tinytapeout-template-v2/src/morph_engine.sv"
    production_rtl_path = ROOT / "rtl/morph_engine_v2.sv"
    test_source = test_path.read_text(encoding="utf-8")
    functions = read_test_functions(test_source)

    xml_root = ET.parse(RESULTS_XML).getroot()
    xml_tests = {}
    for case in xml_root.iter("testcase"):
        name = case.attrib.get("name", "").rsplit(".", 1)[-1]
        if any(case.find(tag) is not None for tag in ("failure", "error")):
            status = "FAIL"
        elif case.find("skipped") is not None:
            status = "SKIP"
        else:
            status = "PASS"
        xml_tests[name] = {
            "status": status,
            "classname": case.attrib.get("classname"),
            "time_seconds": case.attrib.get("time"),
            "failure_message": (
                case.find("failure").attrib.get("message")
                if case.find("failure") is not None else None
            ),
        }

    cases = []
    for name, spec in REQUIREMENTS.items():
        observed = xml_tests.get(name)
        function_source = functions.get(name, "")
        marker_results = [
            {"marker": marker, "present": marker in function_source}
            for marker in spec["markers"]
        ]
        marker_ok = bool(function_source) and all(
            item["present"] for item in marker_results
        )

        cases.append({
            "protocol": spec["protocol"],
            "test_name": name,
            "status": observed["status"] if observed else "MISSING",
            "simulated_this_run": observed is not None,
            "source_assertions_present": marker_ok,
            "source_assertion_markers": marker_results,
            "engine_matches_production_rtl": (
                sha256(tt_engine_path) == sha256(production_rtl_path)
            ),
            "requirements": spec["requirements"],
            "program_file": spec["program"],
            "program_sha256": sha256(ROOT / spec["program"]),
            "hex_file": spec["hex"],
            "hex_sha256": sha256(ROOT / spec["hex"]),
            "test_time_seconds": (
                observed["time_seconds"] if observed else None
            ),
            "failure_message": (
                observed["failure_message"] if observed else None
            ),
        })

    names = [case.attrib.get("name", "").rsplit(".", 1)[-1]
             for case in xml_root.iter("testcase")]
    failures = [
        name for name, record in xml_tests.items()
        if record["status"] == "FAIL"
    ]
    skipped = [
        name for name, record in xml_tests.items()
        if record["status"] == "SKIP"
    ]
    required_failures = [
        case["test_name"] for case in cases
        if case["status"] != "PASS"
        or not case["source_assertions_present"]
        or not case["engine_matches_production_rtl"]
    ]

    report = {
        "schema_version": 1,
        "run_type": "fresh_tinytapeout_v2_cocotb_run",
        "results_xml_sha256": sha256(RESULTS_XML),
        "sources": {
            "production_rtl_sha256": sha256(production_rtl_path),
            "tinytapeout_engine_sha256": sha256(tt_engine_path),
            "wrapper_sha256": sha256(wrapper_path),
            "test_source_sha256": sha256(test_path),
            "engine_matches_production_rtl": (
                sha256(tt_engine_path) == sha256(production_rtl_path)
            ),
        },
        "summary": {
            "xml_testcase_count": len(names),
            "suite_failures": len(failures),
            "suite_failure_names": failures,
            "suite_skipped": len(skipped),
            "required_protocol_cases": len(cases),
            "required_protocol_cases_passed": sum(
                case["test_name"] not in required_failures
                for case in cases
            ),
            "failed_expected_tests": len(required_failures),
            "failed_expected_test_names": required_failures,
        },
        "cases": cases,
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS / "protocol_sim_evidence.json"
    md_path = REPORTS / "protocol_sim_evidence.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# TRACEFORGE SPI/I2C Simulation Evidence",
        "",
        "- Source: fresh TinyTapeout V2 Cocotb run",
        f"- XML testcases: {len(names)}",
        f"- Suite failures: {len(failures)}",
        f"- Required protocol cases passed: {report['summary']['required_protocol_cases_passed']}/{len(cases)}",
        f"- Production RTL and TinyTapeout engine identical: {report['sources']['engine_matches_production_rtl']}",
        "",
        "| Protocol | Test | Result | Source assertions | Engine matches production RTL |",
        "|---|---|---|---|---|",
    ]
    for case in cases:
        lines.append(
            f"| {case['protocol'].upper()} | {case['test_name']} "
            f"| {case['status']} | {case['source_assertions_present']} "
            f"| {case['engine_matches_production_rtl']} |"
        )
    lines.extend([
        "",
        "The evidence records the outcomes of the named Cocotb tests in this run. "
        "It also verifies that the test source contains the expected protocol assertions.",
        "",
        f"Production RTL SHA-256: `{report['sources']['production_rtl_sha256']}`",
        f"TinyTapeout engine SHA-256: `{report['sources']['tinytapeout_engine_sha256']}`",
        f"Test source SHA-256: `{report['sources']['test_source_sha256']}`",
        "",
    ])
    md_path.write_text("\n".join(lines) + "\n")

    print("SIMULATION EVIDENCE SUMMARY:")
    print(json.dumps(report["summary"], indent=2))
    for case in cases:
        print(
            f"{case['protocol'].upper()} {case['test_name']}: "
            f"status={case['status']} "
            f"source_assertions={case['source_assertions_present']} "
            f"engine_match={case['engine_matches_production_rtl']}"
        )
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")


if __name__ == "__main__":
    main()
