import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "traceforge" / "reports"

sys.path.insert(0, str(ROOT / "sim"))
sys.path.insert(0, str(WORK))

from morph_isa_model_v2 import MorphISAModelV2
from traceforge_uart_rtl import expected_snapshot, parse_trace, digest

NOMINAL = 436
IDLE = 10
TAIL = 240


def build_frame(payload, offsets):
    if len(offsets) != 10:
        raise ValueError("Expected ten symbol offsets")

    durations = [NOMINAL + offset for offset in offsets]
    if min(durations) <= 0:
        raise ValueError("Symbol durations must be positive")

    trace = [1] * IDLE
    trace.extend([0] * durations[0])

    for index in range(8):
        trace.extend([((payload >> index) & 1)] * durations[index + 1])

    trace.extend([1] * durations[9])
    trace.extend([1] * TAIL)
    return trace, durations


def main():
    source_report = REPORT_DIR / "uart_rx_minimized_counterexample.json"
    original_vectors = REPORT_DIR / "uart_rx_minimized_counterexample_vectors.hex"
    source = json.loads(source_report.read_text())

    payload = int(source["source_failure"]["payload"], 16)
    offsets = source["minimized"]["offsets"]
    expected_byte = int(source["minimized"]["expected_shift_register"], 16)
    original_rtl_hash = source["source_hashes"]["production_rtl_sha256"]

    rtl = ROOT / "rtl" / "morph_engine_v2.sv"
    firmware = ROOT / "protocols" / "v2_uart_rx_a6.hex"
    tb = WORK / "morph_engine_v2_traceforge_tb.sv"

    current_rtl_hash = digest(rtl)
    if current_rtl_hash != original_rtl_hash:
        raise SystemExit(
            "STOP: production RTL hash differs from the minimized source failure. "
            "Review the change before replaying."
        )

    program = [
        int(line.strip(), 16)
        for line in firmware.read_text().splitlines()
        if line.strip()
    ]

    pins, durations = build_frame(payload, offsets)
    saved_pins = [
        int(line.strip(), 16)
        for line in original_vectors.read_text().splitlines()
        if line.strip()
    ]

    if pins != saved_pins:
        raise SystemExit(
            "STOP: reconstructed waveform differs from the saved minimized vector."
        )

    build_dir = WORK / "obj_dir_counterexample_replay"
    if build_dir.exists():
        raise SystemExit(
            f"STOP: build directory already exists: {build_dir}"
        )

    build = subprocess.run(
        [
            "verilator", "--binary", "--timing", "-Wno-fatal",
            "--top-module", "morph_engine_v2_diff_tb",
            "--Mdir", str(build_dir), str(rtl), str(tb)
        ],
        cwd=ROOT, capture_output=True, text=True, timeout=180
    )

    if build.returncode:
        raise RuntimeError(build.stdout + "\n" + build.stderr)

    (WORK / "morph_v2_program.hex").write_text(
        "".join(
            f"{word:04x}\n"
            for word in program + [0] * (64 - len(program))
        )
    )
    (WORK / "morph_v2_vectors.hex").write_text(
        "".join(f"{pin:02x}\n" for pin in pins)
    )

    model = MorphISAModelV2()
    model.load_program(program)
    expected = [expected_snapshot(model.step(rst_n=False, pin_in=0))]
    expected.extend(
        expected_snapshot(model.step(pin_in=pin))
        for pin in pins
    )

    executable = build_dir / "Vmorph_engine_v2_diff_tb"
    run = subprocess.run(
        [str(executable), f"+N={len(pins)}"],
        cwd=ROOT, capture_output=True, text=True, timeout=120
    )

    if run.returncode:
        raise RuntimeError(
            run.stdout[-4000:] + "\n" + run.stderr[-4000:]
        )

    actual = parse_trace(run.stdout)
    mismatch = None

    if len(actual) != len(expected):
        mismatch = {
            "kind": "trace_length",
            "rtl_cycles": len(actual),
            "model_cycles": len(expected)
        }
    else:
        for index, (got, want) in enumerate(zip(actual, expected)):
            if got != want:
                mismatch = {
                    "kind": "cycle_mismatch",
                    "trace_index": index,
                    "rtl": list(got),
                    "model": list(want)
                }
                break

    if not actual:
        raise RuntimeError("The simulator produced no trace.")

    final = actual[-1]
    observed_byte = final[6]
    error_flag = bool((final[3] & final[4]) & 0x80)
    core_fault = bool(final[9])

    silent_misdecode = (
        observed_byte != expected_byte
        and not error_flag
        and not core_fault
    )

    report = {
        "tool": "TRACEFORGE",
        "version": "0.7.1",
        "test": "replay minimized UART counterexample",
        "source_seed": source["source_failure"]["seed"],
        "payload": f"0x{payload:02X}",
        "symbol_offsets_cycles": offsets,
        "symbol_durations_cycles": durations,
        "input_cycles": len(pins),
        "saved_waveform_matches_reconstruction": pins == saved_pins,
        "rtl_reference_model_cycle_match": mismatch is None,
        "first_mismatch": mismatch,
        "expected_shift_register": f"0x{expected_byte:02X}",
        "observed_shift_register": f"0x{observed_byte:02X}",
        "error_flag_pin7": error_flag,
        "core_fault": core_fault,
        "silent_misdecode_reproduced": silent_misdecode,
        "production_rtl_sha256": current_rtl_hash,
        "replay_passed": (
            mismatch is None
            and silent_misdecode
            and pins == saved_pins
        )
    }

    json_path = REPORT_DIR / "uart_rx_counterexample_replay_report.json"
    md_path = REPORT_DIR / "uart_rx_counterexample_replay_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# TRACEFORGE — Counterexample Replay",
        "",
        f"- Source seed: `{report['source_seed']}`",
        f"- Input byte: `{report['payload']}`",
        f"- Expected shift register: `{report['expected_shift_register']}`",
        f"- Observed shift register: `{report['observed_shift_register']}`",
        f"- Silent misdecode reproduced: `{silent_misdecode}`",
        f"- RTL/reference-model cycle match: `{mismatch is None}`",
        f"- Error flag: `{error_flag}`",
        f"- Core fault: `{core_fault}`",
        f"- Saved waveform matches reconstruction: `{pins == saved_pins}`",
        f"- Production RTL SHA-256: `{current_rtl_hash}`",
        "",
        "This is a reproducible simulation counterexample for the tested waveform. "
        "Its validity against a specified UART timing contract must be assessed separately.",
        ""
    ]
    md_path.write_text("\n".join(lines))

    print("REPLAY REPORT:", json.dumps(report, sort_keys=True))
    print("JSON:", json_path)
    print("MARKDOWN:", md_path)

    if not report["replay_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
