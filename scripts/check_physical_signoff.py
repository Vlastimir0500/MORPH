#!/usr/bin/env python3
"""Fail the MORPH physical-design job on final post-route electrical/timing violations.

The TinyTapeout/LibreLane flow can finish its GDS generation while the final
parasitic STA reports still contain max-fanout, max-slew, max-capacitance, setup,
or hold violations.  This gate reads the *final* 55-openroad-stapostpnr reports,
not intermediate pre-antenna-repair reports.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

CHECK_COUNTS = {
    "max_slew": "max slew violation count",
    "max_fanout": "max fanout violation count",
    "max_cap": "max cap violation count",
}

TIMING_METRIC_SUFFIXES = (
    "timing__hold_vio__count__corner:",
    "timing__hold_r2r_vio__count__corner:",
    "timing__setup_vio__count__corner:",
    "timing__setup_r2r_vio__count__corner:",
)

METRIC_LINE = re.compile(r"^%OL_METRIC_I\s+(\S+)\s+(\S+)\s*$")
COUNT_LINE = re.compile(r"^\s*(max slew|max fanout|max cap) violation count\s+(\d+)\s*$", re.I)


class SignoffReportError(RuntimeError):
    """Raised when required final signoff evidence is missing or malformed."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SignoffReportError(f"cannot read {path}: {exc}") from exc


def _parse_checks_report(path: Path) -> tuple[dict[str, int], list[str]]:
    text = _read_text(path)
    counts: dict[str, int] = {}
    for line in text.splitlines():
        match = COUNT_LINE.match(line)
        if not match:
            continue
        label = match.group(1).lower().replace(" ", "_")
        counts[label] = int(match.group(2))

    missing = sorted(set(CHECK_COUNTS) - set(counts))
    if missing:
        raise SignoffReportError(
            f"{path}: missing required check counters: {', '.join(missing)}"
        )

    violation_rows = [line.strip() for line in text.splitlines() if "(VIOLATED)" in line]
    return counts, violation_rows


def _parse_sta_metrics(path: Path, corner: str) -> dict[str, int]:
    text = _read_text(path)
    values: dict[str, int] = {}
    for line in text.splitlines():
        match = METRIC_LINE.match(line)
        if not match:
            continue
        key, raw_value = match.groups()
        for required in TIMING_METRIC_SUFFIXES:
            if key.startswith(required):
                try:
                    values[required] = int(float(raw_value))
                except ValueError as exc:
                    raise SignoffReportError(
                        f"{path}: non-integer timing metric {key}={raw_value}"
                    ) from exc

    missing = [metric for metric in TIMING_METRIC_SUFFIXES if metric not in values]
    if missing:
        raise SignoffReportError(
            f"{path}: missing timing metrics for {corner}: "
            + ", ".join(metric.removesuffix("__corner:") for metric in missing)
        )
    return values


def check_signoff_directory(reports_dir: Path) -> dict[str, Any]:
    """Validate post-route antenna/DRC and all configured post-PNR STA corners."""
    config_path = reports_dir / "config.json"
    config = json.loads(_read_text(config_path))
    corners = config.get("STA_CORNERS")
    if not isinstance(corners, list) or not corners:
        raise SignoffReportError(f"{config_path}: STA_CORNERS is missing or empty")

    results: dict[str, Any] = {}
    failures: list[str] = []

    # Detailed routing performs a second antenna-repair pass after global routing.
    # That pass can add diode loads after intermediate timing repair has completed,
    # so validate its *final* metrics as well as the later parasitic STA reports.
    route_dir = reports_dir.parent / "44-openroad-detailedrouting"
    route_log_path = route_dir / "openroad-detailedrouting.log"
    route_metrics_path = route_dir / "or_metrics_out.json"
    route_log = _read_text(route_log_path)
    route_metrics = json.loads(_read_text(route_metrics_path))
    for key in ("route__drc_errors", "antenna__violating__nets", "antenna__violating__pins"):
        if key not in route_metrics:
            raise SignoffReportError(f"{route_metrics_path}: required metric {key} is missing")
        value = int(route_metrics[key])
        if value != 0:
            failures.append(f"detailed routing: {key} = {value}")

    net_antenna_checks = re.findall(r"\[INFO ANT-0002\] Found (\d+) net violations\.", route_log)
    pin_antenna_checks = re.findall(r"\[INFO ANT-0001\] Found (\d+) pin violations\.", route_log)
    if not net_antenna_checks or not pin_antenna_checks:
        raise SignoffReportError(f"{route_log_path}: final antenna check results are missing")
    final_net_antenna = int(net_antenna_checks[-1])
    final_pin_antenna = int(pin_antenna_checks[-1])
    if final_net_antenna != 0:
        failures.append(f"detailed routing: final antenna net violations = {final_net_antenna}")
    if final_pin_antenna != 0:
        failures.append(f"detailed routing: final antenna pin violations = {final_pin_antenna}")

    results["detailed_routing"] = {
        "route_drc_errors": int(route_metrics["route__drc_errors"]),
        "antenna_violating_nets": int(route_metrics["antenna__violating__nets"]),
        "antenna_violating_pins": int(route_metrics["antenna__violating__pins"]),
        "final_antenna_net_violations": final_net_antenna,
        "final_antenna_pin_violations": final_pin_antenna,
        "antenna_diodes_inserted_or_present": int(route_metrics.get("antenna_diodes_count", 0)),
    }

    for corner in corners:
        corner_dir = reports_dir / corner
        checks_path = corner_dir / "checks.rpt"
        sta_log_path = corner_dir / "sta.log"
        if not checks_path.is_file() or not sta_log_path.is_file():
            raise SignoffReportError(
                f"{corner}: expected both checks.rpt and sta.log under {corner_dir}"
            )

        check_counts, violation_rows = _parse_checks_report(checks_path)
        timing_counts = _parse_sta_metrics(sta_log_path, corner)
        results[corner] = {
            **check_counts,
            "timing": {
                metric.removesuffix("__corner:"): value
                for metric, value in timing_counts.items()
            },
            "violating_pins": violation_rows,
        }

        for metric, count in check_counts.items():
            if count != 0:
                failures.append(f"{corner}: {metric} violations = {count}")
        for metric, count in timing_counts.items():
            if count != 0:
                failures.append(
                    f"{corner}: {metric.removesuffix('__corner:')} = {count}"
                )

    return {
        "status": "FAIL" if failures else "PASS",
        "reports_dir": str(reports_dir),
        "corners_checked": list(corners),
        "corners": results,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("runs/wokwi/55-openroad-stapostpnr"),
        help="final post-PNR STA report directory",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=Path("build/physical-signoff-gate.json"),
        help="where to write the machine-readable gate result",
    )
    args = parser.parse_args()

    try:
        result = check_signoff_directory(args.reports_dir)
    except (SignoffReportError, json.JSONDecodeError) as exc:
        result = {
            "status": "ERROR",
            "reports_dir": str(args.reports_dir),
            "failures": [str(exc)],
        }

    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"MORPH FINAL PHYSICAL SIGNOFF: {result['status']}")
    routing = result.get("detailed_routing")
    if routing:
        print(
            "  detailed routing: "
            f"DRC={routing['route_drc_errors']}, "
            f"antenna nets={routing['final_antenna_net_violations']}, "
            f"antenna pins={routing['final_antenna_pin_violations']}, "
            f"antenna diodes={routing['antenna_diodes_inserted_or_present']}"
        )
    for corner, details in result.get("corners", {}).items():
        if corner == "detailed_routing":
            continue
        print(
            f"  {corner}: fanout={details['max_fanout']}, "
            f"slew={details['max_slew']}, cap={details['max_cap']}"
        )
        for pin in details.get("violating_pins", []):
            print(f"    {pin}")
    for failure in result.get("failures", []):
        print(f"ERROR: {failure}", file=sys.stderr)
    print(f"Report: {args.report_json}")

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
