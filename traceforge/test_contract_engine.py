import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from contract_engine import (
    ContractAuditError,
    get_path,
    matches_where,
    strict_equal,
    evaluate_check,
)


class ContractEngineTests(unittest.TestCase):
    def test_nested_report_path(self):
        data = {"summary": {"counts": {"correct_decode": 570}}}
        self.assertEqual(get_path(data, "summary.counts.correct_decode"), 570)

    def test_boolean_is_not_integer(self):
        self.assertFalse(strict_equal(True, 1))
        self.assertTrue(strict_equal(True, True))

    def test_range_filter(self):
        self.assertTrue(matches_where(
            {"period": 436},
            {"period": {"gte": 413, "lte": 460}}
        ))
        self.assertFalse(matches_where(
            {"period": 461},
            {"period": {"gte": 413, "lte": 460}}
        ))

    def test_all_cases_match(self):
        data = {"cases": [
            {"period": 436, "classification": "correct_decode", "match": True},
            {"period": 436, "classification": "correct_decode", "match": True},
            {"period": 470, "classification": "silent_misdecode", "match": True},
        ]}

        result = evaluate_check(
            {
                "id": "nominal_cases",
                "kind": "all_cases_match",
                "report": "fake.json",
                "cases_path": "cases",
                "where": {"period": {"eq": 436}},
                "assertions": {
                    "classification": "correct_decode",
                    "match": True
                },
                "min_matches": 2,
            },
            Path.cwd(),
            lambda unused: data,
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["matched_cases"], 2)

    def test_minimum_match_count_prevents_vacuous_pass(self):
        result = evaluate_check(
            {
                "id": "nonempty",
                "kind": "all_cases_match",
                "report": "fake.json",
                "cases_path": "cases",
                "where": {"period": {"eq": 436}},
                "assertions": {"classification": "correct_decode"},
                "min_matches": 1,
            },
            Path.cwd(),
            lambda unused: {"cases": []},
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["matched_cases"], 0)

    def test_missing_path_raises(self):
        with self.assertRaises(ContractAuditError):
            get_path({"actual": 1}, "missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
