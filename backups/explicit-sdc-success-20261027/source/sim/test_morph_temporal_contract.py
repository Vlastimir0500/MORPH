import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
from morph_contract import ContractError, verify_program


CONTRACT_PATH = ROOT / "protocols" / "edge_timed_release.contract.json"
SOURCE_PATH = ROOT / "protocols" / "edge_timed_release.morph"


class TemporalContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.source = SOURCE_PATH.read_text(encoding="utf-8")

    def test_reference_model_matches_exact_temporal_schedule(self):
        report = verify_program(self.source, self.contract, str(SOURCE_PATH))
        self.assertEqual(report["status"], "PASS")
        scenario = report["temporal_scenarios"][0]
        self.assertEqual(scenario["status"], "PASS")
        self.assertEqual(
            scenario["observed_transitions"]["pin_out_transitions"],
            [{"cycle": 6, "value": 1}, {"cycle": 18, "value": 0}],
        )
        self.assertEqual(
            scenario["observed_transitions"]["shift_reg_transitions"],
            [{"cycle": 16, "value": 1}],
        )

    def test_one_cycle_timing_regression_fails_contract(self):
        self.contract["temporal_scenarios"][0]["expect"]["pin_out_transitions"][0]["cycle"] = 7
        report = verify_program(self.source, self.contract)
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["temporal_scenarios"][0]["signal_checks"][0]["passed"])

    def test_invalid_pin_value_is_rejected(self):
        self.contract["temporal_scenarios"][0]["pin_trace"][2] = 2
        with self.assertRaises(ContractError):
            verify_program(self.source, self.contract)

    def test_invalid_expected_cycle_is_rejected(self):
        self.contract["temporal_scenarios"][0]["expect"]["pin_out_transitions"][0]["cycle"] = 999
        with self.assertRaises(ContractError):
            verify_program(self.source, self.contract)


if __name__ == "__main__":
    unittest.main(verbosity=2)
