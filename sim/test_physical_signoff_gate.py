import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_physical_signoff import check_signoff_directory, SignoffReportError  # noqa: E402


CORNERS = ["nom_fast_1p32V_m40C", "nom_slow_1p08V_125C", "nom_typ_1p20V_25C"]


def _write_corner(reports_dir: Path, corner: str, fanout: int = 0, setup: int = 0):
    corner_dir = reports_dir / corner
    corner_dir.mkdir(parents=True)
    checks = f"""
max slew violation count 0
max fanout violation count {fanout}
max cap violation count 0
"""
    if fanout:
        checks += "\nmax fanout\nPin Limit Fanout Slack\nfanout532/X 8 13 -5 (VIOLATED)\n"
    (corner_dir / "checks.rpt").write_text(checks, encoding="utf-8")

    metric_lines = []
    for base in (
        "timing__hold_vio__count__corner:",
        "timing__hold_r2r_vio__count__corner:",
        "timing__setup_vio__count__corner:",
        "timing__setup_r2r_vio__count__corner:",
    ):
        value = setup if base.startswith("timing__setup") else 0
        metric_lines.append(f"%OL_METRIC_I {base}{corner} {value}")
    (corner_dir / "sta.log").write_text("\n".join(metric_lines) + "\n", encoding="utf-8")


def _make_reports(tmp_path: Path, fanout: int = 0, setup: int = 0) -> Path:
    reports_dir = tmp_path / "55-openroad-stapostpnr"
    reports_dir.mkdir()
    (reports_dir / "config.json").write_text(
        json.dumps({"STA_CORNERS": CORNERS}), encoding="utf-8"
    )
    route_dir = tmp_path / "44-openroad-detailedrouting"
    route_dir.mkdir()
    (route_dir / "openroad-detailedrouting.log").write_text(
        "[INFO ANT-0002] Found 0 net violations.\n"
        "[INFO ANT-0001] Found 0 pin violations.\n",
        encoding="utf-8",
    )
    (route_dir / "or_metrics_out.json").write_text(
        json.dumps({
            "route__drc_errors": 0,
            "antenna__violating__nets": 0,
            "antenna__violating__pins": 0,
            "antenna_diodes_count": 2,
        }),
        encoding="utf-8",
    )
    for corner in CORNERS:
        _write_corner(reports_dir, corner, fanout=fanout, setup=setup)
    return reports_dir


def test_signoff_gate_passes_all_corners_when_clean(tmp_path):
    result = check_signoff_directory(_make_reports(tmp_path))
    assert result["status"] == "PASS"
    assert result["corners_checked"] == CORNERS
    assert result["failures"] == []


def test_signoff_gate_rejects_final_fanout_violation(tmp_path):
    result = check_signoff_directory(_make_reports(tmp_path, fanout=1))
    assert result["status"] == "FAIL"
    assert any("max_fanout violations = 1" in item for item in result["failures"])
    assert any("fanout532/X" in item for item in result["corners"][CORNERS[0]]["violating_pins"])


def test_signoff_gate_rejects_setup_or_hold_metric_violation(tmp_path):
    result = check_signoff_directory(_make_reports(tmp_path, setup=1))
    assert result["status"] == "FAIL"
    assert any("timing__setup_vio__count" in item for item in result["failures"])


def test_signoff_gate_fails_closed_when_corner_report_is_missing(tmp_path):
    reports_dir = _make_reports(tmp_path)
    (reports_dir / CORNERS[-1] / "sta.log").unlink()
    with pytest.raises(SignoffReportError):
        check_signoff_directory(reports_dir)


def test_signoff_gate_rejects_residual_antenna_violations(tmp_path):
    reports_dir = _make_reports(tmp_path)
    route_dir = tmp_path / "44-openroad-detailedrouting"
    (route_dir / "openroad-detailedrouting.log").write_text(
        "[INFO ANT-0002] Found 2 net violations.\n"
        "[INFO ANT-0001] Found 1 pin violations.\n",
        encoding="utf-8",
    )
    result = check_signoff_directory(reports_dir)
    assert result["status"] == "FAIL"
    assert any("antenna net violations = 2" in item for item in result["failures"])
    assert any("antenna pin violations = 1" in item for item in result["failures"])


@pytest.mark.parametrize(
    ("report_line", "metric"),
    [
        ("max slew violation count 0", "max_slew"),
        ("max cap violation count 0", "max_cap"),
    ],
)
def test_signoff_gate_rejects_slew_and_cap_violations(
    tmp_path, report_line, metric
):
    reports_dir = _make_reports(tmp_path)
    checks_path = reports_dir / CORNERS[0] / "checks.rpt"

    text = checks_path.read_text(encoding="utf-8")
    checks_path.write_text(
        text.replace(report_line, report_line[:-1] + "1"),
        encoding="utf-8",
    )

    result = check_signoff_directory(reports_dir)
    assert result["status"] == "FAIL"
    assert any(f"{metric} violations = 1" in item for item in result["failures"])


def test_signoff_gate_rejects_hold_metric_violation(tmp_path):
    reports_dir = _make_reports(tmp_path)
    sta_path = reports_dir / CORNERS[0] / "sta.log"

    text = sta_path.read_text(encoding="utf-8")
    old = f"%OL_METRIC_I timing__hold_vio__count__corner:{CORNERS[0]} 0"
    new = f"%OL_METRIC_I timing__hold_vio__count__corner:{CORNERS[0]} 1"

    assert old in text
    sta_path.write_text(text.replace(old, new), encoding="utf-8")

    result = check_signoff_directory(reports_dir)
    assert result["status"] == "FAIL"
    assert any("timing__hold_vio__count" in item for item in result["failures"])


def test_signoff_gate_rejects_detailed_route_drc_error(tmp_path):
    reports_dir = _make_reports(tmp_path)
    metrics_path = (
        reports_dir.parent
        / "44-openroad-detailedrouting"
        / "or_metrics_out.json"
    )

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["route__drc_errors"] = 1
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")

    result = check_signoff_directory(reports_dir)
    assert result["status"] == "FAIL"
    assert any("route__drc_errors = 1" in item for item in result["failures"])


def test_signoff_gate_rejects_missing_antenna_metric(tmp_path):
    reports_dir = _make_reports(tmp_path)
    metrics_path = (
        reports_dir.parent
        / "44-openroad-detailedrouting"
        / "or_metrics_out.json"
    )

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    del metrics["antenna__violating__nets"]
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")

    with pytest.raises(SignoffReportError):
        check_signoff_directory(reports_dir)
