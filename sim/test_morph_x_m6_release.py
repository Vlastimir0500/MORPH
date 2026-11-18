"""M6 release-evidence checks: strict failure modes and non-destructive audit."""
from __future__ import annotations

import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import morph_x_m6_release as m6


def good_run(name, sha):
    return {"name": name, "status": "completed", "conclusion": "success",
            "head_sha": sha, "html_url": "https://github.com/Vlastimir0500/MORPH/actions/runs/1"}


def good_jobs(names):
    return {"jobs": [{"name": n, "status": "completed", "conclusion": "success",
                      "id": i + 100, "html_url": "https://github.com/test"}
                     for i, n in enumerate(names)]}


@pytest.mark.parametrize("path,expected", [
    ("backups/foo/out.log", "historical_backups_review"),
    ("traceforge/synth/file.sv", "traceforge_historical_review"),
    ("tinytapeout-template/src/project.v", "legacy_tinytapeout_review"),
    ("formal/invalid_opcode/log.txt", "formal_experiment_history_review"),
    ("formal/qualification/run.sh", "active_or_unclassified_keep"),
    ("sim/__pycache__/a.pyc", "generated_artifact_review"),
    ("reports/trace.vcd", "generated_artifact_review"),
    ("compiler/morph_x_protocol_zero.py", "active_or_unclassified_keep"),
    ("tinytapeout-template-v2/src/morph_engine.sv", "active_or_unclassified_keep"),
])
def test_classification_is_review_only(path, expected):
    assert m6.classify_path(path) == expected


def test_sha256_file(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"abc")
    assert m6.sha256_file(p) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_ci_accepts_exact_commit_and_all_jobs():
    sha = "a" * 40
    good = m6.validate_ci_run(good_run("MORPH Engineering Gates", sha),
                               good_jobs(m6.ENGINEERING_JOBS), sha,
                               "MORPH Engineering Gates", m6.ENGINEERING_JOBS)
    assert good["qualified"] and len(good["jobs"]) == 6


@pytest.mark.parametrize("mutation", [
    "wrong-commit", "bad-name", "running", "failed-run", "missing-job",
    "failed-job", "skipped-job", "duplicate-job", "missing-list"
])
def test_ci_rejects_invalid_evidence(mutation):
    sha = "b" * 40
    run = good_run("MORPH Engineering Gates", sha)
    jobs = good_jobs(m6.ENGINEERING_JOBS)
    if mutation == "wrong-commit":
        run["head_sha"] = "c" * 40
    elif mutation == "bad-name":
        run["name"] = "Wrong workflow"
    elif mutation == "running":
        run["status"] = "in_progress"
    elif mutation == "failed-run":
        run["conclusion"] = "failure"
    elif mutation == "missing-job":
        jobs["jobs"].pop()
    elif mutation == "failed-job":
        jobs["jobs"][0]["conclusion"] = "failure"
    elif mutation == "skipped-job":
        jobs["jobs"][0]["conclusion"] = "skipped"
    elif mutation == "duplicate-job":
        jobs["jobs"].append(dict(jobs["jobs"][0]))
    else:
        jobs = {}
    with pytest.raises(m6.ReleaseGateError):
        m6.validate_ci_run(run, jobs, sha, "MORPH Engineering Gates", m6.ENGINEERING_JOBS)


def test_formal_has_separate_exact_commit_gate():
    sha = "d" * 40
    formal = m6.validate_ci_run(good_run("MORPH V2 Formal Qualification", sha),
                                good_jobs(m6.FORMAL_JOBS), sha,
                                "MORPH V2 Formal Qualification", m6.FORMAL_JOBS)
    assert [x["name"] for x in formal["jobs"]] == ["formal-qualification"]


def test_bundle_fails_without_evidence(tmp_path):
    with pytest.raises(m6.ReleaseGateError, match="Missing evidence"):
        m6.make_bundle(tmp_path, tmp_path / "out.zip", tmp_path / "audit.json",
                       tmp_path / "ci.json", tmp_path / "qual.json")


@pytest.mark.parametrize("mutation", ["audit-fail", "ci-fail", "qual-fail", "sha-mismatch"])
def test_bundle_fails_closed(tmp_path, monkeypatch, mutation):
    monkeypatch.setattr(m6, "run", lambda root, *command: "f" * 40)
    a = {"source_checks_passed": True, "git_commit": "f" * 40}
    b = {"qualified": True, "source_commit": "f" * 40}
    c = {"overall_status": "PASS", "git_commit": "f" * 40}
    if mutation == "audit-fail":
        a["source_checks_passed"] = False
    elif mutation == "ci-fail":
        b["qualified"] = False
    elif mutation == "qual-fail":
        c["overall_status"] = "INCOMPLETE"
    else:
        a["git_commit"] = "e" * 40
    for name, value in (("a.json", a), ("b.json", b), ("c.json", c)):
        (tmp_path / name).write_text(json.dumps(value))
    with pytest.raises(m6.ReleaseGateError):
        m6.make_bundle(tmp_path, tmp_path / "out.zip", tmp_path / "a.json",
                       tmp_path / "b.json", tmp_path / "c.json")


def test_source_safety_disclaimers_are_present():
    text = " ".join(m6.SCOPE_NOTICES)
    assert "Simultaneous" in text
    assert "silicon" in text
    assert "blind external" in text


def test_actual_release_sources_match_frozen_hardware_and_workflow():
    checks = m6.check_sources(ROOT)
    failures = [x for x in checks if not x["pass"]]
    assert not failures, failures
