"""M5 protocol-neutral oracle, challenge host and strict negative controls."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))

from morph_x_protocol_zero import (
    SPEC_SCHEMA, OBS_SCHEMA, ChallengeError, validate_spec, spec_to_ir,
    generate_selftest_spec, capture_fixture_from_spec, compare_capture_to_spec,
    make_observation, judge_observation, digest,
)
from morph_x_multireplay import ReplayError, compile_and_verify_multi

SCRIPT = ROOT / "compiler/morph_x_protocol_zero.py"
PULSE = ROOT / "examples/morph_x_pulse_link_challenge.json"


def sample_spec():
    return json.loads(PULSE.read_text(encoding="utf-8"))


def observed(spec, *, source="offline-synthetic"):
    return make_observation(spec, copy.deepcopy(spec["events"]), source=source,
                            released=True)


def test_pulse_link_protocol_contract_and_model():
    spec = sample_spec()
    validate_spec(spec)
    assert spec["clock_hz"] == 50_000_000
    assert spec["pins"] == [0, 1, 2, 3]
    assert len(spec["events"]) == 8
    result = compile_and_verify_multi(spec_to_ir(spec))
    assert result["report"]["verification"]["model_verified"]
    assert result["report"]["verification"]["all_pins_released"]
    assert result["report"]["expected_relative_cycles"] == spec["events"]


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 7, 42, 77, 1234, 65535, 0x5EED17, 0xB105D, 0xFFFFFFFF])
def test_seeded_specs_compile_to_exact_v2_model(seed):
    spec = generate_selftest_spec(seed)
    assert spec == generate_selftest_spec(seed)
    assert spec["challenge_id"].startswith("SELFTEST-")
    assert len(spec["events"]) == 8
    assert sorted({e["pin"] for e in spec["events"]}) == [0, 1, 2, 3]
    result = compile_and_verify_multi(spec_to_ir(spec))
    assert result["report"]["expected_relative_cycles"] == spec["events"]
    assert result["report"]["verification"]["all_pins_released"]
    assert result["report"]["instruction_count"] <= 64


@pytest.mark.parametrize("seed", [0, 1, 17, 99, 65535, 0x5EED17])
def test_synthetic_capture_matches_prior_challenge(seed):
    spec = generate_selftest_spec(seed)
    frame = capture_fixture_from_spec(spec, initial_stamp=65530)
    checked = compare_capture_to_spec(frame, spec)
    assert checked["capture_verified"]
    assert checked["event_count"] == 8
    assert len(checked["capture_sha256"]) == 64


def test_fixture_capture_not_external_hardware_evidence():
    spec = sample_spec()
    frame = capture_fixture_from_spec(spec)
    assert compare_capture_to_spec(frame, spec)["capture_verified"]
    # Internal synthetic proof is specifically marked in the independent oracle.
    report = judge_observation(spec, observed(spec))
    assert report["accepted"]
    assert report["source"] == "offline-synthetic"
    assert report["blind_external_evaluation_claimed"] is False


def test_oracle_accepts_full_matching_observation():
    spec = sample_spec()
    verdict = judge_observation(spec, observed(spec, source="rtl-top"))
    assert verdict["accepted"]
    assert all(verdict["conditions"].values())
    assert verdict["first_difference_index"] is None
    assert verdict["challenge_sha256"] == digest(spec)


@pytest.mark.parametrize("mutation", ["timing", "value", "pin", "drop", "extra", "release", "fault", "other-drive"])
def test_independent_oracle_rejects_falsified_observations(mutation):
    spec = sample_spec()
    obs = observed(spec)
    if mutation == "timing":
        obs["transitions"][3]["cycle"] += 1
    elif mutation == "value":
        obs["transitions"][3]["value"] ^= 1
    elif mutation == "pin":
        obs["transitions"][3]["pin"] = 7
    elif mutation == "drop":
        obs["transitions"].pop()
    elif mutation == "extra":
        obs["transitions"].append({"cycle": 500, "pin": 3, "value": 1})
    elif mutation == "release":
        obs["released"] = False
    elif mutation == "fault":
        obs["fault"] = True
    elif mutation == "other-drive":
        obs["unselected_output_enable_seen"] = True
    v = judge_observation(spec, obs)
    assert not v["accepted"]
    if mutation in {"timing", "value", "pin", "drop", "extra"}:
        assert not v["conditions"]["exact_transitions"]
    else:
        assert v["conditions"]["exact_transitions"]


@pytest.mark.parametrize("mutation", ["wrong-id", "wrong-schema", "unknown-source", "missing", "extra", "nonboolean", "bad-cycle", "bad-pin", "bad-value", "unhashable-source"])
def test_bad_observation_fails_closed(mutation):
    spec = sample_spec()
    obs = observed(spec)
    if mutation == "wrong-id":
        obs["challenge_id"] = "OTHER"
    elif mutation == "wrong-schema":
        obs["schema"] = "v0"
    elif mutation == "unknown-source":
        obs["source"] = "secret-fake-ASIC"
    elif mutation == "missing":
        del obs["released"]
    elif mutation == "extra":
        obs["garbage"] = True
    elif mutation == "nonboolean":
        obs["released"] = 1
    elif mutation == "bad-cycle":
        obs["transitions"][0]["cycle"] = True
    elif mutation == "bad-pin":
        obs["transitions"][0]["pin"] = 8
    elif mutation == "bad-value":
        obs["transitions"][0]["value"] = -1
    elif mutation == "unhashable-source":
        obs["source"] = ["rtl-top"]
    with pytest.raises(ChallengeError):
        judge_observation(spec, obs)


@pytest.mark.parametrize("mutation", ["schema", "fields", "id", "boolclock", "clk", "pins", "pinbool", "initial", "empty", "too-many", "wrongpin", "repeated", "outoforder", "missing-pin", "bad-boolean"])
def test_invalid_challenge_rejected(mutation):
    spec = sample_spec()
    if mutation == "schema":
        spec["schema"] = "bad"
    elif mutation == "fields":
        spec["unknown"] = 0
    elif mutation == "id":
        spec["challenge_id"] = "../../secret"
    elif mutation == "boolclock":
        spec["clock_hz"] = True
    elif mutation == "clk":
        spec["clock_hz"] = 25_000_000
    elif mutation == "pins":
        spec["pins"] = [1, 0, 2, 3]
    elif mutation == "pinbool":
        spec["pins"][0] = True
    elif mutation == "initial":
        spec["initial_levels"] = 256
    elif mutation == "empty":
        spec["events"] = []
    elif mutation == "too-many":
        spec["events"] = spec["events"] + [spec["events"][0]]
    elif mutation == "wrongpin":
        spec["events"][0]["pin"] = 7
    elif mutation == "repeated":
        spec["events"][3]["value"] = 1
    elif mutation == "outoforder":
        spec["events"][4]["cycle"] = 1
    elif mutation == "missing-pin":
        spec["events"] = [e for e in spec["events"] if e["pin"] != 3]
    elif mutation == "bad-boolean":
        spec["events"][0]["cycle"] = True
    with pytest.raises(ChallengeError):
        validate_spec(spec)


def test_simultaneous_challenge_is_valid_input_but_rejected_by_backend():
    spec = sample_spec()
    # Keep analog-agnostic source challenge permissive; backend must reject.
    spec["events"][1]["cycle"] = spec["events"][0]["cycle"]
    validate_spec(spec)
    with pytest.raises(ReplayError, match="simultaneous"):
        compile_and_verify_multi(spec_to_ir(spec))


@pytest.mark.parametrize("gap", [1, 3])
def test_unrepresentable_external_gap_is_rejected_not_quantized(gap):
    spec = sample_spec()
    spec["events"][1]["cycle"] = gap
    validate_spec(spec)
    with pytest.raises(ReplayError, match="unrepresentable"):
        compile_and_verify_multi(spec_to_ir(spec))


def test_malformed_first_capture_edge_rejected():
    spec = sample_spec()
    frame = capture_fixture_from_spec(spec)
    frame["slots"][0][1] = 0x02
    with pytest.raises(ChallengeError, match="first capture edge"):
        compare_capture_to_spec(frame, spec)


def test_capture_wrong_value_and_timing_rejected():
    spec = sample_spec()
    for change in ["wrong-pin-value", "timing"]:
        frame = capture_fixture_from_spec(spec)
        if change == "wrong-pin-value":
            frame["slots"][2][0] ^= 1 << 2
        else:
            frame["slots"][2][2] += 1
        with pytest.raises(ChallengeError):
            compare_capture_to_spec(frame, spec)


def test_overflow_does_not_count_as_pass():
    spec = sample_spec()
    frame = capture_fixture_from_spec(spec)
    frame["status"] |= 0x10
    with pytest.raises(ChallengeError, match="overflow"):
        compare_capture_to_spec(frame, spec)


def test_cli_generate_prepare_judge_roundtrip(tmp_path):
    spec_file = tmp_path / "synthetic.json"
    cmd = [sys.executable, str(SCRIPT)]
    r = subprocess.run([*cmd, "generate-selftest", "--seed", "456",
                        "--output", str(spec_file)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    spec = json.loads(spec_file.read_text())
    assert spec["challenge_id"] == "SELFTEST-000001C8"
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(capture_fixture_from_spec(spec)))
    out = tmp_path / "result"
    r = subprocess.run([*cmd, "prepare", str(spec_file), "--capture", str(capture),
                        "--output-dir", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "NOT YET AN INDEPENDENT" in r.stdout
    assert (out / "challenge.hex").read_text().strip()
    provenance = json.loads((out / "challenge.provenance.json").read_text())
    assert not provenance["external_blind_challenge_verified"]
    assert provenance["source_capture_check"]["capture_verified"]
    obs_file = tmp_path / "observation.json"
    obs_file.write_text(json.dumps(observed(spec)))
    verdict_file = tmp_path / "verdict.json"
    r = subprocess.run([*cmd, "judge", str(spec_file), str(obs_file),
                        "--output", str(verdict_file)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(verdict_file.read_text())["accepted"]


def test_cli_negative_judge_exit_one(tmp_path):
    spec = sample_spec()
    a, b, out = [tmp_path / name for name in ["spec.json", "badobs.json", "judge.json"]]
    a.write_text(json.dumps(spec))
    bad = observed(spec)
    bad["transitions"][2]["cycle"] += 1
    b.write_text(json.dumps(bad))
    r = subprocess.run([sys.executable, str(SCRIPT), "judge", str(a), str(b),
                        "--output", str(out)], capture_output=True, text=True)
    assert r.returncode == 1
    assert not json.loads(out.read_text())["accepted"]


def test_cli_unsupported_challenge_exit_two_and_no_program(tmp_path):
    spec = sample_spec()
    spec["events"][1]["cycle"] = 1
    a, out = tmp_path / "spec.json", tmp_path / "out"
    a.write_text(json.dumps(spec))
    r = subprocess.run([sys.executable, str(SCRIPT), "prepare", str(a),
                        "--output-dir", str(out)], capture_output=True, text=True)
    assert r.returncode == 2
    assert not (out / "challenge.hex").exists()
