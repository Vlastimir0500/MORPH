#!/usr/bin/env python3
"""MORPH X M6: non-destructive source audit, exact-commit CI attestation and release bundle.

No network API calls during `audit`; `check-ci` requires an authenticated GitHub CLI.
This tool does not delete files, alter RTL, submit an ASIC, or claim fabricated silicon.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

REPO = "Vlastimir0500/MORPH"
BASELINE = {
    "rtl/morph_engine_v2.sv": "ebaad3f79ba71e2f958133a92d7d24a269396c161d89b4f51fda201d0895de98",
    "protocols/v2_uart_rx_a6.hex": "5a61cb59f5ccfabe6c10e92fc70b94a8bf3da34a136b76e1cc6e07adecb2ac5a",
}
ENGINEERING_JOBS = (
    "rtl-regression", "tinytapeout-rtl", "gds", "precheck",
    "gate-level-test", "Final post-route physical gate",
)
FORMAL_JOBS = ("formal-qualification",)
REQUIRED_CORE = (
    "rtl/morph_engine_v2.sv", "tinytapeout-template-v2/src/morph_engine.sv",
    "tinytapeout-template-v2/src/morph_x_trace_capture.sv",
    "tinytapeout-template-v2/src/project.v",
    "tinytapeout-template-v2/test/test.py",
    "tinytapeout-template-v2/test/Makefile",
    "tinytapeout-template-v2/info.yaml",
    "tinytapeout-template-v2/src/config.json",
    "compiler/morph_x_trace.py", "compiler/morph_x_host.py",
    "compiler/morph_x_replay.py", "compiler/morph_x_multireplay.py",
    "compiler/morph_x_protocol_zero.py",
    "sim/test_morph_x_replay_rtl.py", "sim/test_morph_x_multireplay_rtl.py",
    "sim/test_morph_x_protocol_zero_rtl.py", "sim/test_morph_x_m6_release.py",
    "formal/qualification/run.sh",
    "scripts/check_physical_signoff.py", "scripts/run_full_qualification.py",
    "scripts/morph_x_m6_release.py",
    ".github/workflows/morph-engineering.yml",
    ".github/workflows/morph-formal-qualification.yml",
    "docs/MORPH_X_M6_RELEASE_CHECKLIST.md",
    "docs/MORPH_X_M6_LIMITATIONS.md",
)
# Preserve the qualification result's actual provenance. This is NOT independent validation.
SCOPE_NOTICES = (
    "Model/RTL verification is not fabricated silicon validation",
    "The captured protocol has a maximum of eight source events",
    "16-bit timestamp wrap can make long intervals ambiguous",
    "Simultaneous multi-pin transitions are unsupported by the current V2 ISA",
    "A blind external Protocol Zero challenge has not been evidenced",
    "No measured silicon power, frequency, electrical compliance or MTBF",
)


class ReleaseGateError(RuntimeError):
    pass


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(root: Path, *command: str) -> str:
    p = subprocess.run(list(command), cwd=root, text=True, capture_output=True, check=False)
    if p.returncode != 0:
        raise ReleaseGateError(f"{command!r} exited {p.returncode}: {p.stderr.strip()[-700:]}")
    return p.stdout.strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_path(path: str) -> str:
    """Classify, DO NOT imply safe deletion."""
    if path.startswith("backups/"):
        return "historical_backups_review"
    if path.startswith("traceforge/"):
        return "traceforge_historical_review"
    if path.startswith("tinytapeout-template/"):
        return "legacy_tinytapeout_review"
    if path.startswith("formal/") and not path.startswith("formal/qualification/"):
        return "formal_experiment_history_review"
    if re.search(r"(?:/__pycache__/|/\.pytest_cache/|\.pyc$|\.log$|\.vcd$|\.fst$)", path):
        return "generated_artifact_review"
    return "active_or_unclassified_keep"


def files_tracked(root: Path) -> list[str]:
    p = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=False)
    if p.returncode:
        raise ReleaseGateError("Cannot list git-tracked files")
    return sorted(os.fsdecode(x) for x in p.stdout.split(b"\0") if x)


def check_sources(root: Path) -> list[dict]:
    """Strict source-level checks; outputs are explicit, evidence is not inflated."""
    results = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append({"name": name, "pass": bool(condition), "detail": detail})

    for path in REQUIRED_CORE:
        check("required:" + path, (root / path).is_file())
    for rel, expected in BASELINE.items():
        p = root / rel
        actual = sha256_file(p) if p.is_file() else "MISSING"
        check("frozen_sha256:" + rel, actual == expected, f"actual={actual}")
    rtl = root / "rtl/morph_engine_v2.sv"
    mirror = root / "tinytapeout-template-v2/src/morph_engine.sv"
    check("engine_mirror_matches", rtl.is_file() and mirror.is_file() and rtl.read_bytes() == mirror.read_bytes())
    try:
        cfg = json.loads((root / "tinytapeout-template-v2/src/config.json").read_text())
    except (OSError, ValueError) as e:
        cfg = {}
        check("valid_ihp_config_json", False, str(e))
    else:
        check("valid_ihp_config_json", True)
    expected_config = {
        "DESIGN_NAME": "tt_um_rattandeep_morph_v2",
        "CLOCK_PERIOD": 20,
        "CTS_SINK_CLUSTERING_SIZE": 4,
        "CTS_DISTANCE_BETWEEN_BUFFERS": 36,
        "PNR_SDC_FILE": "dir::morph_pnr.sdc",
        "SIGNOFF_SDC_FILE": "dir::morph_signoff.sdc",
        "RUN_POST_GRT_DESIGN_REPAIR": True,
    }
    for key, expected in expected_config.items():
        check("physical_config:" + key, type(cfg.get(key)) is type(expected) and cfg.get(key) == expected, repr(cfg.get(key)))

    # TinyTapeout generates the effective flow source list from info.yaml. Do
    # not misinterpret src/config.json's VERILOG_FILES alone as its effective
    # compiled sources; the GDS artifact must additionally prove actual inclusion.
    info_path = root / "tinytapeout-template-v2/info.yaml"
    info = info_path.read_text() if info_path.is_file() else ""
    section = re.search(r"(?m)^\s*source_files\s*:\s*\n((?:\s+-[^\n]*\n)+)", info)
    listed = re.findall(r"^\s*-\s*['\"]?([\w.-]+)", section.group(1), flags=re.M) if section else []
    for name in ("project.v", "morph_engine.sv", "morph_x_trace_capture.sv"):
        check("tt_info_source:" + name, name in listed, f"source_files={listed}")

    mk_path = root / "tinytapeout-template-v2/test/Makefile"
    makefile = mk_path.read_text() if mk_path.is_file() else ""
    check("cocotb_compiles_capture", bool(re.search(r"^PROJECT_SOURCES\s*=.*\bmorph_x_trace_capture\.sv\b", makefile, re.M)))

    wf_path = root / ".github/workflows/morph-engineering.yml"
    wf = wf_path.read_text() if wf_path.is_file() else ""
    for job in ("rtl-regression", "tinytapeout-rtl", "gds", "physical-signoff", "precheck", "gate-level-test"):
        check("workflow_job:" + job, bool(re.search(r"^  " + re.escape(job) + r":\s*$", wf, re.M)))
    check("workflow_contains_m6_gate", "python3 scripts/morph_x_m6_release.py audit --strict" in wf)
    check("formal_workflow_exists", (root / ".github/workflows/morph-formal-qualification.yml").is_file())
    return results


def scan_source_references(root: Path, tracked: list[str]) -> list[dict]:
    matches = []
    for rel in tracked:
        if not (rel == "README.md" or rel.startswith((".github/", "compiler/", "docs/", "scripts/", "sim/", "rtl/", "protocols/", "tinytapeout-template-v2/"))):
            continue
        if not rel.endswith((".md", ".txt", ".py", ".yml", ".yaml", ".json", ".sh", ".sv", ".v")):
            continue
        p = root / rel
        if not p.is_file() or p.stat().st_size > 300_000:
            continue
        try:
            value = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # One occurrence per file is enough for a manual dependency review.
        refs = [part for part in ("backups/", "traceforge/", "tinytapeout-template/") if part in value]
        if refs:
            matches.append({"file": rel, "referenced_candidates": refs})
    return matches


def make_audit(root: Path) -> dict:
    checks = check_sources(root)
    tracked = files_tracked(root)
    buckets = defaultdict(lambda: {"tracked_files": 0, "working_tree_bytes": 0, "missing_checkout_files": 0})
    for rel in tracked:
        bucket = buckets[classify_path(rel)]
        bucket["tracked_files"] += 1
        path = root / rel
        try:
            bucket["working_tree_bytes"] += path.stat().st_size
        except OSError:
            bucket["missing_checkout_files"] += 1
    crucial = [p for p in tracked if classify_path(p) == "active_or_unclassified_keep"
               and p.startswith((".github/", "compiler/", "docs/", "examples/", "rtl/", "scripts/", "sim/", "protocols/", "tinytapeout-template-v2/src/", "tinytapeout-template-v2/test/"))]
    manifests = []
    for rel in crucial:
        file = root / rel
        if file.is_file() and not file.is_symlink():
            manifests.append({"path": rel, "sha256": sha256_file(file)})
    failed = [r["name"] for r in checks if not r["pass"]]
    try:
        sha = run(root, "git", "rev-parse", "HEAD")
    except ReleaseGateError:
        sha = None
    return {
        "schema": "morph-x.m6.source-audit.v1", "timestamp_utc": iso_now(),
        "git_commit": sha, "source_checks_passed": not failed,
        "failed_checks": failed, "checks": checks,
        "tracked_file_count": len(tracked),
        "classifications": dict(sorted(buckets.items())),
        "cleanup_candidates_are_not_safe_to_delete_automatically": True,
        "source_references_to_review": scan_source_references(root, tracked),
        "active_source_manifest": manifests,
        "scope_notices": list(SCOPE_NOTICES),
        "blind_external_protocol_zero_trial": "NOT_EVIDENCED",
        "fabricated_silicon_measurements": "NONE",
    }


def validate_ci_run(run_obj: dict, jobs_obj: dict, expected_sha: str,
                    expected_workflow: str, required_jobs: tuple[str, ...]) -> dict:
    if run_obj.get("head_sha") != expected_sha:
        raise ReleaseGateError(f"CI head SHA mismatch for {expected_workflow}: {run_obj.get('head_sha')}")
    if run_obj.get("name") != expected_workflow:
        raise ReleaseGateError(f"Wrong workflow name: {run_obj.get('name')}")
    if run_obj.get("status") != "completed" or run_obj.get("conclusion") != "success":
        raise ReleaseGateError(f"Workflow not successful: {expected_workflow}: {run_obj.get('conclusion')}")
    all_jobs = jobs_obj.get("jobs")
    if not isinstance(all_jobs, list):
        raise ReleaseGateError("GitHub jobs API returned no jobs list")
    evidence = []
    for name in required_jobs:
        matches = [j for j in all_jobs if j.get("name") == name]
        if len(matches) != 1:
            raise ReleaseGateError(f"Expected one job named {name!r}, found {len(matches)}")
        job = matches[0]
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            raise ReleaseGateError(f"Failed/incomplete CI job {name!r}: {job.get('conclusion')!r}")
        evidence.append({"name": name, "job_id": job.get("id"), "conclusion": "success", "html_url": job.get("html_url")})
    return {"workflow": expected_workflow, "head_sha": expected_sha,
            "url": run_obj.get("html_url"), "jobs": evidence, "qualified": True}


def gh_json(root: Path, endpoint: str) -> dict:
    text = run(root, "gh", "api", endpoint)
    try:
        return json.loads(text)
    except ValueError as e:
        raise ReleaseGateError(f"Invalid GitHub API response for {endpoint}") from e


def check_remote_ci(root: Path, engineering_id: int, formal_id: int) -> dict:
    sha = run(root, "git", "rev-parse", "HEAD")
    e = gh_json(root, f"repos/{REPO}/actions/runs/{engineering_id}")
    ej = gh_json(root, f"repos/{REPO}/actions/runs/{engineering_id}/jobs?per_page=100")
    f = gh_json(root, f"repos/{REPO}/actions/runs/{formal_id}")
    fj = gh_json(root, f"repos/{REPO}/actions/runs/{formal_id}/jobs?per_page=100")
    return {"schema": "morph-x.m6.ci-attestation.v1", "checked_utc": iso_now(),
            "source_commit": sha, "qualified": True,
            "engineering_run_id": engineering_id, "formal_run_id": formal_id,
            "engineering": validate_ci_run(e, ej, sha, "MORPH Engineering Gates", ENGINEERING_JOBS),
            "formal": validate_ci_run(f, fj, sha, "MORPH V2 Formal Qualification", FORMAL_JOBS),
            "scope_notices": list(SCOPE_NOTICES),
            "blind_external_protocol_zero_trial": "NOT_EVIDENCED"}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_bundle(root: Path, output: Path, audit_path: Path, ci_path: Path, qual_path: Path) -> dict:
    for path in (audit_path, ci_path, qual_path):
        if not path.is_file():
            raise ReleaseGateError("Missing evidence: " + str(path))
    audit, ci, qual = [json.loads(p.read_text()) for p in (audit_path, ci_path, qual_path)]
    sha = run(root, "git", "rev-parse", "HEAD")
    if not audit.get("source_checks_passed") or audit.get("git_commit") != sha:
        raise ReleaseGateError("Audit does not pass or belongs to another commit")
    if not ci.get("qualified") or ci.get("source_commit") != sha:
        raise ReleaseGateError("CI is not qualified for this exact commit")
    if qual.get("overall_status") != "PASS" or qual.get("git_commit") != sha:
        raise ReleaseGateError("Local full qualification is not PASS on this commit")
    pieces = {
        "evidence/source-audit.json": audit_path,
        "evidence/github-ci-attestation.json": ci_path,
        "evidence/full-qualification.json": qual_path,
        "README.md": root / "README.md",
        "docs/MORPH_X_M6_RELEASE_CHECKLIST.md": root / "docs/MORPH_X_M6_RELEASE_CHECKLIST.md",
        "docs/MORPH_X_M6_LIMITATIONS.md": root / "docs/MORPH_X_M6_LIMITATIONS.md",
    }
    for path in pieces.values():
        if not path.is_file():
            raise ReleaseGateError(f"Missing bundle input: {path}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for arc, path in pieces.items():
            z.write(path, arcname=arc)
        z.writestr("README_EVIDENCE.txt",
                   "MORPH X M6 evidence only. Source checkout on GitHub is the authority.\n"
                   "Simulation and signoff reports are not fabricated silicon measurements.\n"
                   "External blind Protocol Zero trial remains unevidenced.\n")
    return {"path": str(output), "size_bytes": output.stat().st_size,
            "sha256": sha256_file(output), "source_commit": sha, "files": sorted(pieces)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "check-ci", "bundle"))
    parser.add_argument("--strict", action="store_true", help="Audit returns exit code 1 if source checks fail")
    parser.add_argument("--engineering", type=int, help="GitHub engineering run ID")
    parser.add_argument("--formal", type=int, help="GitHub formal run ID")
    parser.add_argument("--audit-file", type=Path, default=Path("build/morph-x-m6/source-audit.json"))
    parser.add_argument("--ci-file", type=Path, default=Path("build/morph-x-m6/github-ci-attestation.json"))
    parser.add_argument("--qualification-file", type=Path, default=Path("build/qualification/qualification-report.json"))
    parser.add_argument("--bundle-file", type=Path, default=Path("build/morph-x-m6/morph-x-m6-evidence.zip"))
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        if args.action == "audit":
            audit = make_audit(root)
            write_json(root / args.audit_file, audit)
            print(f"M6 SOURCE AUDIT: {'PASS' if audit['source_checks_passed'] else 'FAIL'}; "
                  f"tracked={audit['tracked_file_count']}; review classifications:")
            for k, v in sorted(audit["classifications"].items()):
                print(f"  {k}: {v['tracked_files']} files / {v['working_tree_bytes']:,} bytes")
            print(f"Report: {root / args.audit_file}")
            if audit["failed_checks"]:
                print("FAILED CHECKS: " + ", ".join(audit["failed_checks"]))
            print("No files removed. External blind challenge is not evidenced.")
            return 1 if args.strict and not audit["source_checks_passed"] else 0
        if args.action == "check-ci":
            if args.engineering is None or args.formal is None:
                raise ReleaseGateError("check-ci requires --engineering and --formal run IDs")
            outcome = check_remote_ci(root, args.engineering, args.formal)
            write_json(root / args.ci_file, outcome)
            print("M6 EXACT-COMMIT GITHUB CI: PASS")
            print(f"Report: {root / args.ci_file}")
            return 0
        result = make_bundle(root, root / args.bundle_file, root / args.audit_file,
                             root / args.ci_file, root / args.qualification_file)
        print("M6 EVIDENCE BUNDLE CREATED: " + json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, ReleaseGateError, json.JSONDecodeError) as exc:
        print(f"M6 RELEASE GATE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
