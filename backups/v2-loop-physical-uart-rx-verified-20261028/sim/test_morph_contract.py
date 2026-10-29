import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
from morph_contract import ContractError, run_contract, verify_program

BASE_CONTRACT = {
    "schema_version": 1,
    "name": "test_protocol",
    "source": "program.morph",
    "limits": {"max_program_words": 16, "max_wait_cycles": 16},
    "requirements": {
        "required_mnemonics": ["EDGE", "DRIVE", "WAIT", "SAMPLE", "SHIFT", "BRANCH"],
        "drive_sequence": [1, 0],
        "must_have_backward_branch": True,
    },
}
PROGRAM = """\
start:
    EDGE RISE
    DRIVE 1
    WAIT 4
    SAMPLE
    SHIFT
    DRIVE 0
    BRANCH start
"""


class ContractTests(unittest.TestCase):
    def test_current_protocol_passes_contract(self):
        report = verify_program(PROGRAM, BASE_CONTRACT, "edge_timed_release.morph")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["words_hex"], ["4001", "1001", "3004", "2000", "5000", "1000", "6000"])
        self.assertTrue(all(c["passed"] for c in report["checks"]))

    def test_wrong_drive_sequence_fails(self):
        contract = json.loads(json.dumps(BASE_CONTRACT))
        contract["requirements"]["drive_sequence"] = [0, 1]
        report = verify_program(PROGRAM, contract)
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(next(c for c in report["checks"] if c["id"] == "drive_sequence")["passed"])

    def test_wait_over_budget_fails(self):
        contract = json.loads(json.dumps(BASE_CONTRACT))
        contract["limits"]["max_wait_cycles"] = 3
        report = verify_program(PROGRAM, contract)
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(next(c for c in report["checks"] if c["id"] == "wait_bound")["passed"])

    def test_missing_required_instruction_fails(self):
        contract = json.loads(json.dumps(BASE_CONTRACT))
        report = verify_program("DRIVE 1\nDRIVE 0\nBRANCH 0", contract)
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(next(c for c in report["checks"] if c["id"] == "required_mnemonics")["passed"])

    def test_invalid_schema_rejected(self):
        contract = json.loads(json.dumps(BASE_CONTRACT))
        contract["limits"]["max_program_words"] = 17
        with self.assertRaises(ContractError):
            verify_program(PROGRAM, contract)

    def test_cli_workflow_writes_auditable_report(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "program.morph").write_text(PROGRAM, encoding="utf-8")
            (directory / "program.contract.json").write_text(json.dumps(BASE_CONTRACT), encoding="utf-8")
            report, destination = run_contract(
                directory / "program.contract.json", directory / "out" / "report.json"
            )
            saved = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(saved["source_sha256"], report["source_sha256"])
            self.assertEqual(saved["program_words"], 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
