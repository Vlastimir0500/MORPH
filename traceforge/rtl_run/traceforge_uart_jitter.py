import json
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "traceforge" / "reports"

sys.path.insert(0, str(ROOT / "sim"))
sys.path.insert(0, str(WORK))

from morph_isa_model_v2 import MorphISAModelV2
from traceforge_uart_rtl import digest, expected_snapshot, parse_trace

PAYLOADS = [0x00, 0x55, 0x81, 0xA5, 0xA6]
NOMINAL = 436
JITTER_LIMIT = 20
TRIALS_PER_PAYLOAD = 30
IDLE = 10
TAIL = 240


def reverse_byte(value):
    return int(f"{value:08b}"[::-1], 2)


def build_jittered_frame(payload, durations):
    trace = [1] * IDLE
    trace.extend([0] * durations[0])
    for index in range(8):
        trace.extend([((payload >> index) & 1)] * durations[index + 1])
    trace.extend([1] * durations[9])
    trace.extend([1] * TAIL)
    return trace


def main():
    rtl = ROOT / "rtl" / "morph_engine_v2.sv"
    tb = WORK / "morph_engine_v2_traceforge_tb.sv"
    firmware = ROOT / "protocols" / "v2_uart_rx_a6.hex"
    program = [
        int(line.strip(), 16)
        for line in firmware.read_text().splitlines()
        if line.strip()
    ]

    build_dir = WORK / "obj_dir_jitter"
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

    executable = build_dir / "Vmorph_engine_v2_diff_tb"
    program_path = WORK / "morph_v2_program.hex"
    vectors_path = WORK / "morph_v2_vectors.hex"
    program_path.write_text(
        "".join(f"{word:04x}\n" for word in program + [0] * (64 - len(program)))
    )

    results = []

    for payload in PAYLOADS:
        for trial in range(TRIALS_PER_PAYLOAD):
            rng = random.Random(20261028 + payload * 1000 + trial)
            offsets = [
                rng.randint(-JITTER_LIMIT, JITTER_LIMIT)
                for _ in range(10)
            ]
            durations = [NOMINAL + offset for offset in offsets]
            pins = build_jittered_frame(payload, durations)

            vectors_path.write_text(
                "".join(f"{pin:02x}\n" for pin in pins)
            )

            model = MorphISAModelV2()
            model.load_program(program)
            expected = [expected_snapshot(model.step(rst_n=False, pin_in=0))]
            expected.extend(
                expected_snapshot(model.step(pin_in=pin))
                for pin in pins
            )

            run = subprocess.run(
                [str(executable), f"+N={len(pins)}"],
                cwd=ROOT, capture_output=True, text=True, timeout=120
            )
            if run.returncode:
                raise RuntimeError(
                    f"Simulation failed for payload 0x{payload:02X}, "
                    f"trial {trial}:\n{run.stdout[-2000:]}\n{run.stderr[-2000:]}"
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
                raise RuntimeError("Simulator returned an empty trace.")

            final = actual[-1]
            shift = final[6]
            error_flag = bool((final[3] & final[4]) & 0x80)
            fault = bool(final[9])

            if mismatch:
                classification = "rtl_model_mismatch"
            elif error_flag:
                classification = "error_flagged"
            elif fault:
                classification = "core_fault"
            elif shift == reverse_byte(payload):
                classification = "correct_decode"
            else:
                classification = "silent_misdecode"

            results.append({
                "payload": f"0x{payload:02X}",
                "trial": trial,
                "seed": 20261028 + payload * 1000 + trial,
                "symbol_durations_cycles": durations,
                "symbol_offsets_cycles": offsets,
                "rtl_model_match": mismatch is None,
                "first_mismatch": mismatch,
                "expected_shift_register": f"0x{reverse_byte(payload):02X}",
                "observed_shift_register": f"0x{shift:02X}",
                "error_flag_pin7": error_flag,
                "core_fault": fault,
                "classification": classification
            })

    counts = Counter(item["classification"] for item in results)
    by_payload = []

    for payload in PAYLOADS:
        subset = [
            item for item in results
            if item["payload"] == f"0x{payload:02X}"
        ]
        by_payload.append({
            "payload": f"0x{payload:02X}",
            "trials": len(subset),
            "counts": dict(sorted(Counter(
                item["classification"] for item in subset
            ).items()))
        })

    report = {
        "tool": "TRACEFORGE",
        "version": "0.5.0",
        "experiment": "Deterministic per-symbol UART timing jitter",
        "parameters": {
            "nominal_period_cycles": NOMINAL,
            "jitter_limit_cycles": JITTER_LIMIT,
            "trials_per_payload": TRIALS_PER_PAYLOAD,
            "payloads": [f"0x{value:02X}" for value in PAYLOADS],
            "total_cases": len(results),
            "seed_policy": "fixed seed derived from payload and trial index"
        },
        "source_hashes": {
            "production_rtl_sha256": digest(rtl),
            "uart_rx_hex_sha256": digest(firmware),
            "isolated_testbench_sha256": digest(tb)
        },
        "summary": {
            "total": len(results),
            "counts": dict(sorted(counts.items())),
            "rtl_model_mismatches": sum(
                not item["rtl_model_match"] for item in results
            ),
            "silent_misdecode_rate": round(
                counts["silent_misdecode"] / len(results), 4
            )
        },
        "by_payload": by_payload,
        "cases": results
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "uart_rx_jitter_report.json"
    md_path = REPORT_DIR / "uart_rx_jitter_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# TRACEFORGE v0.5 — UART Jitter Experiment",
        "",
        f"- Total cases: {len(results)}",
        f"- Nominal symbol period: {NOMINAL} cycles",
        f"- Per-symbol jitter: ±{JITTER_LIMIT} cycles",
        f"- Fixed, reproducible seeds: yes",
        "",
        "| Payload | Correct | Error flagged | Silent misdecode | RTL/model mismatch |",
        "|---|---:|---:|---:|---:|"
    ]

    for item in by_payload:
        c = item["counts"]
        lines.append(
            f"| {item['payload']} | {c.get('correct_decode', 0)} "
            f"| {c.get('error_flagged', 0)} "
            f"| {c.get('silent_misdecode', 0)} "
            f"| {c.get('rtl_model_mismatch', 0)} |"
        )

    lines.extend([
        "",
        "The experiment uses synthetic independent timing offsets for the start, "
        "data and stop symbol durations. It is a deterministic stress experiment, "
        "not a claim about a universal UART timing specification.",
        "",
        f"Production RTL SHA-256: `{report['source_hashes']['production_rtl_sha256']}`",
        ""
    ])
    md_path.write_text("\n".join(lines) + "\n")

    print(f"Jitter experiment: {len(results)} cases")
    print("SUMMARY:", json.dumps(report["summary"], sort_keys=True))
    for item in by_payload:
        print(item["payload"], item["counts"])
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")

    if report["summary"]["rtl_model_mismatches"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
