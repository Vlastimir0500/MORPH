import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
from morph_contract_v2 import ContractError, run_contract, verify_contract

CONTRACT_PATH = ROOT / "protocols" / "v2_edge_timed_release.contract.json"
EXPECTED_ASSEMBLY_PATH = ROOT / "protocols" / "v2_edge_timed_release.expected.morph"


class V2TemporalContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_contract_compiles_to_expected_v2_program_and_passes_scenarios(self):
        report = verify_contract(self.contract, str(CONTRACT_PATH))
        expected_source = EXPECTED_ASSEMBLY_PATH.read_text(encoding="utf-8")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["generated_source"], expected_source)
        self.assertEqual(report["words_hex"], ["1001", "400D", "7000", "0000"])
        self.assertEqual([item["status"] for item in report["scenarios"]], ["PASS", "PASS"])
        self.assertEqual(report["scenarios"][0]["observed_transitions"]["pin_oe"], [
            {"cycle": 3, "value": 1}, {"cycle": 9, "value": 0}
        ])
        self.assertEqual(report["scenarios"][1]["observed_transitions"]["pin_oe"], [
            {"cycle": 3, "value": 1}, {"cycle": 11, "value": 0}
        ])

    def test_one_cycle_expected_timing_mutation_is_caught(self):
        changed = json.loads(json.dumps(self.contract))
        changed["scenarios"][1]["expect"]["transitions"]["pin_oe"][1]["cycle"] = 10
        report = verify_contract(changed)
        self.assertEqual(report["status"], "FAIL")
        check = next(item for item in report["scenarios"][1]["transition_checks"] if item["signal"] == "pin_oe")
        self.assertFalse(check["passed"])

    def test_shorter_timeout_mutation_is_caught(self):
        changed = json.loads(json.dumps(self.contract))
        changed["program"][1]["timeout_cycles"] = 5
        report = verify_contract(changed)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["scenarios"][1]["status"], "FAIL")

    def test_unbounded_edge_wait_cannot_bypass_timeout_limit(self):
        changed = json.loads(json.dumps(self.contract))
        changed["program"][1]["timeout_cycles"] = 0
        report = verify_contract(changed)

        self.assertEqual(report["status"], "FAIL")
        check = next(
            item for item in report["static_checks"]
            if item["id"] == "edge_timeout_limit"
        )
        self.assertFalse(check["passed"])
        self.assertEqual(len(check["unbounded_edge_waits"]), 1)

    def test_out_of_range_pin_bus_value_is_rejected(self):
        changed = json.loads(json.dumps(self.contract))
        changed["scenarios"][0]["pin_trace"][0] = 256
        with self.assertRaises(ContractError):
            verify_contract(changed)

    def test_unsupported_operation_is_rejected(self):
        changed = json.loads(json.dumps(self.contract))
        changed["program"].insert(1, {"op": "dma", "channel": 0})
        with self.assertRaises(ContractError):
            verify_contract(changed)

    def test_report_and_generated_assembly_are_written_with_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            report, destination = run_contract(
                CONTRACT_PATH,
                Path(temp) / "report.json",
                Path(temp) / "generated.morph",
            )
            saved = json.loads(destination.read_text(encoding="utf-8"))
            generated = (Path(temp) / "generated.morph").read_text(encoding="utf-8")
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(generated, report["generated_source"])
            self.assertEqual(saved["contract_sha256"], report["contract_sha256"])
            self.assertEqual(saved["generated_source_sha256"], report["generated_source_sha256"])
            self.assertEqual(saved["program_sha256"], report["program_sha256"])
            self.assertEqual(len(saved["program_sha256"]), 64)


    def test_static_limits_and_required_mnemonics_fail_closed(self):
        cases = []

        changed = json.loads(json.dumps(self.contract))
        changed["limits"]["max_program_words"] = 3
        cases.append(("program_word_limit", changed))

        changed = json.loads(json.dumps(self.contract))
        changed["program"].insert(-1, {"op": "wait_cycles", "cycles": 1})
        cases.append(("wait_cycle_limit", changed))

        changed = json.loads(json.dumps(self.contract))
        changed["limits"]["max_edge_timeout_cycles"] = 5
        cases.append(("edge_timeout_limit", changed))

        changed = json.loads(json.dumps(self.contract))
        changed["requirements"]["required_mnemonics"].append("SHIFT")
        cases.append(("required_mnemonics", changed))

        for check_id, changed_contract in cases:
            with self.subTest(check=check_id):
                report = verify_contract(changed_contract)
                check = next(
                    item for item in report["static_checks"]
                    if item["id"] == check_id
                )
                self.assertFalse(check["passed"])
                self.assertEqual(report["status"], "FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
