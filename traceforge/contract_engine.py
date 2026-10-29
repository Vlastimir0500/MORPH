import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_CHECKS = {
    "file_sha256_equals",
    "report_value_equals",
    "all_cases_match",
}


class ContractAuditError(ValueError):
    pass


def strict_equal(actual, expected):
    return type(actual) is type(expected) and actual == expected


def get_path(value, path):
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise ContractAuditError(f"Invalid path: {path}") from exc
        else:
            raise ContractAuditError(f"Path not found: {path}")
    return current


def safe_path(root, relative_path):
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ContractAuditError("Evidence paths must be non-empty strings")

    root = root.resolve()
    path = (root / relative_path).resolve()

    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ContractAuditError(
            f"Evidence path escapes project root: {relative_path}"
        ) from exc

    return path


def matches_condition(actual, condition):
    if not isinstance(condition, dict):
        return strict_equal(actual, condition)

    operators = {"eq", "gte", "lte", "gt", "lt", "in"}
    if not condition or not set(condition).issubset(operators):
        return False

    for operator, expected in condition.items():
        try:
            if operator == "eq" and not strict_equal(actual, expected):
                return False
            if operator == "gte" and not actual >= expected:
                return False
            if operator == "lte" and not actual <= expected:
                return False
            if operator == "gt" and not actual > expected:
                return False
            if operator == "lt" and not actual < expected:
                return False
            if operator == "in" and actual not in expected:
                return False
        except (TypeError, ValueError):
            return False

    return True


def matches_where(record, where):
    for path, condition in where.items():
        try:
            actual = get_path(record, path)
        except ContractAuditError:
            return False
        if not matches_condition(actual, condition):
            return False
    return True


def validate_contract(contract):
    if not isinstance(contract, dict):
        raise ContractAuditError("Contract must be a JSON object")

    if type(contract.get("schema_version")) is not int:
        raise ContractAuditError("schema_version must be an integer")
    if contract["schema_version"] != 1:
        raise ContractAuditError("Unsupported contract schema version")

    if not isinstance(contract.get("name"), str) or not contract["name"].strip():
        raise ContractAuditError("Contract name must be non-empty")

    checks = contract.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ContractAuditError("Contract must contain a non-empty checks list")

    ids = set()
    for check in checks:
        if not isinstance(check, dict):
            raise ContractAuditError("Every check must be an object")

        check_id = check.get("id")
        kind = check.get("kind")

        if not isinstance(check_id, str) or not check_id.strip():
            raise ContractAuditError("Every check requires an id")
        if check_id in ids:
            raise ContractAuditError(f"Duplicate check id: {check_id}")
        ids.add(check_id)

        if kind not in SUPPORTED_CHECKS:
            raise ContractAuditError(f"Unsupported check kind: {kind}")

        required = {
            "file_sha256_equals": {"file", "expected"},
            "report_value_equals": {"report", "path", "expected"},
            "all_cases_match": {
                "report", "cases_path", "where", "assertions", "min_matches"
            },
        }[kind]

        missing = required - check.keys()
        if missing:
            raise ContractAuditError(
                f"Check {check_id} missing fields: {sorted(missing)}"
            )

        if kind == "all_cases_match":
            if not isinstance(check["where"], dict):
                raise ContractAuditError(f"{check_id}.where must be an object")
            if not isinstance(check["assertions"], dict) or not check["assertions"]:
                raise ContractAuditError(f"{check_id}.assertions must be non-empty")
            if (
                type(check["min_matches"]) is not int
                or check["min_matches"] < 1
            ):
                raise ContractAuditError(f"{check_id}.min_matches must be positive")


def evaluate_check(check, root, load_report):
    check_id = check["id"]
    kind = check["kind"]

    if kind == "file_sha256_equals":
        path = safe_path(root, check["file"])
        if not path.is_file():
            raise ContractAuditError(f"Evidence file not found: {check['file']}")

        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = check["expected"]
        passed = strict_equal(actual, expected)

        return {
            "id": check_id,
            "kind": kind,
            "passed": passed,
            "file": check["file"],
            "expected": expected,
            "actual": actual,
        }

    document = load_report(check["report"])

    if kind == "report_value_equals":
        actual = get_path(document, check["path"])
        expected = check["expected"]

        return {
            "id": check_id,
            "kind": kind,
            "passed": strict_equal(actual, expected),
            "report": check["report"],
            "path": check["path"],
            "expected": expected,
            "actual": actual,
        }

    cases = get_path(document, check["cases_path"])
    if not isinstance(cases, list):
        raise ContractAuditError(
            f"{check_id}: {check['cases_path']} must point to a list"
        )

    matched = [
        case for case in cases
        if isinstance(case, dict) and matches_where(case, check["where"])
    ]

    failures = []
    for index, case in enumerate(matched):
        for path, expected in check["assertions"].items():
            try:
                actual = get_path(case, path)
            except ContractAuditError:
                actual = None

            if not strict_equal(actual, expected):
                failures.append({
                    "matched_case_index": index,
                    "path": path,
                    "expected": expected,
                    "actual": actual,
                })

    passed = len(matched) >= check["min_matches"] and not failures

    return {
        "id": check_id,
        "kind": kind,
        "passed": passed,
        "report": check["report"],
        "matched_cases": len(matched),
        "minimum_required": check["min_matches"],
        "assertions_per_case": len(check["assertions"]),
        "failure_count": len(failures),
        "failure_samples": failures[:10],
    }


def audit_contract(contract_path, output_path=None):
    contract_path = Path(contract_path).resolve()
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractAuditError(f"Cannot load contract: {exc}") from exc

    validate_contract(contract)

    cache = {}

    def load_report(relative_path):
        if relative_path not in cache:
            path = safe_path(ROOT, relative_path)
            try:
                cache[relative_path] = json.loads(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise ContractAuditError(
                    f"Cannot load evidence report {relative_path}: {exc}"
                ) from exc
        return cache[relative_path]

    results = [
        evaluate_check(check, ROOT, load_report)
        for check in contract["checks"]
    ]

    passed_count = sum(result["passed"] for result in results)
    report = {
        "schema_version": 1,
        "contract": contract["name"],
        "contract_sha256": hashlib.sha256(
            contract_path.read_bytes()
        ).hexdigest(),
        "status": "PASS" if passed_count == len(results) else "FAIL",
        "checks_passed": passed_count,
        "checks_total": len(results),
        "checks": results,
    }

    if output_path:
        destination = safe_path(ROOT, output_path)
    else:
        destination = ROOT / "traceforge" / "reports" / (
            contract["name"] + ".audit.json"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    markdown = [
        f"# TRACEFORGE Contract Audit: {contract['name']}",
        "",
        f"- Status: **{report['status']}**",
        f"- Checks passed: {passed_count}/{len(results)}",
        "",
        "| Check | Result | Details |",
        "|---|---|---|",
    ]

    for result in results:
        if result["kind"] == "all_cases_match":
            details = (
                f"{result['matched_cases']} matched cases; "
                f"{result['failure_count']} assertion failures"
            )
        elif result["kind"] == "report_value_equals":
            details = f"expected={result['expected']}; actual={result['actual']}"
        else:
            details = f"SHA-256 actual={result['actual']}"

        markdown.append(
            f"| {result['id']} | "
            f"{'PASS' if result['passed'] else 'FAIL'} | {details} |"
        )

    markdown_path = destination.with_suffix(".md")
    markdown_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")

    return report, destination, markdown_path


def main():
    parser = argparse.ArgumentParser(
        description="Run a TRACEFORGE evidence contract"
    )
    parser.add_argument("contract")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()

    try:
        report, destination, markdown_path = audit_contract(
            args.contract, args.output
        )
    except ContractAuditError as exc:
        print(f"CONTRACT ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Contract: {report['contract']}")
    print(f"Status: {report['status']}")
    print(f"Checks: {report['checks_passed']}/{report['checks_total']}")
    print(f"JSON report: {destination}")
    print(f"Markdown report: {markdown_path}")

    for check in report["checks"]:
        print(f"{'PASS' if check['passed'] else 'FAIL'}: {check['id']}")

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
