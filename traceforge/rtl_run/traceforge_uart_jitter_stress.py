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
AMPLITUDES = [20, 40, 60, 80]
TRIALS = 30
NOMINAL = 436
IDLE = 10
TAIL = 240


def reverse_byte(value):
    return int(f"{value:08b}"[::-1], 2)


def build_frame(payload, durations):
    trace = [1] * IDLE
    trace.extend([0] * durations[0])
    for bit in range(8):
        trace.extend([((payload >> bit) & 1)] * durations[bit + 1])
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

    build_dir = WORK / "obj_dir_jitter_stress"
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
    program_file = WORK / "morph_v2_program.hex"
    vector_file = WORK / "morph_v2_vectors.hex"

    program_file.write_text(
        "".join(f"{word:04x}\n" for word in program + [0] * (64 - len(program)))
    )

    results = []

    for amplitude in AMPLITUDES:
        for payload in PAYLOADS:
            for trial in range(TRIALS):
                seed = 20261028 + amplitude * 100000 + payload * 1000 + trial
                rng = random.Random(seed)
                offsets = [rng.randint(-amplitude, amplitude) for _ in range(10)]
                durations = [NOMINAL + offset for offset in offsets]
                pins = build_frame(payload, durations)

                vector_file.write_text("".join(f"{pin:02x}\n" for pin in pins))

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
                        f"Simulation failed at amplitude={amplitude}, "
                        f"payload=0x{payload:02X}, trial={trial}:\n"
                        f"{run.stdout[-2000:]}\n{run.stderr[-2000:]}"
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
                    "amplitude_cycles": amplitude,
                    "payload": f"0x{payload:02X}",
                    "trial": trial,
                    "seed": seed,
                    "symbol_offsets_cycles": offsets,
                    "symbol_durations_cycles": durations,
                    "rtl_model_match": mismatch is None,
                    "first_mismatch": mismatch,
                    "expected_shift_register": f"0x{reverse_byte(payload):02X}",
                    "observed_shift_register": f"0x{shift:02X}",
                    "error_flag_pin7": error_flag,
                    "core_fault": fault,
                    "classification": classification
                })

    by_amplitude = []
    for amplitude in AMPLITUDES:
        subset = [r for r in results if r["amplitude_cycles"] == amplitude]
        by_amplitude.append({
            "amplitude_cycles": amplitude,
            "cases": len(subset),
            "counts": dict(sorted(Counter(
                r["classification"] for r in subset
            ).items()))
        })

    counts = Counter(r["classification"] for r in results)
    mismatches = [r for r in results if not r["rtl_model_match"]]
    failures = [r for r in results if r["classification"] != "correct_decode"]

    report = {
        "tool": "TRACEFORGE",
        "version": "0.6.0",
        "experiment": "Deterministic UART per-symbol jitter stress",
        "parameters": {
            "nominal_period_cycles": NOMINAL,
            "jitter_amplitudes_cycles": AMPLITUDES,
            "payloads": [f"0x{x:02X}" for x in PAYLOADS],
            "trials_per_payload_and_amplitude": TRIALS,
            "total_cases": len(results),
            "seed_policy": "fixed seed derived from amplitude, payload and trial"
        },
        "source_hashes": {
            "production_rtl_sha256": digest(rtl),
            "uart_rx_hex_sha256": digest(firmware),
            "isolated_testbench_sha256": digest(tb)
        },
        "summary": {
            "total": len(results),
            "counts": dict(sorted(counts.items())),
            "rtl_model_mismatches": len(mismatches),
            "non_correct_cases": len(failures)
        },
        "by_amplitude": by_amplitude,
        "first_failure_examples": failures[:12],
        "cases": results
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "uart_rx_jitter_stress_report.json"
    md_path = REPORT_DIR / "uart_rx_jitter_stress_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# TRACEFORGE v0.6 — UART Jitter Stress",
        "",
        f"- Total RTL simulations: {len(results)}",
        f"- RTL/reference-model mismatches: {len(mismatches)}",
        "",
        "| Jitter amplitude | Cases | Correct decode | Error flagged | Silent misdecode | Core fault |",
        "|---:|---:|---:|---:|---:|---:|"
    ]

    for item in by_amplitude:
        c = item["counts"]
        lines.append(
            f"| ±{item['amplitude_cycles']} | {item['cases']} "
            f"| {c.get('correct_decode', 0)} "
            f"| {c.get('error_flagged', 0)} "
            f"| {c.get('silent_misdecode', 0)} "
            f"| {c.get('core_fault', 0)} |"
        )

    lines.extend([
        "",
        "## First non-correct cases",
        "",
        "| Amplitude | Payload | Trial | Seed | Classification | Offsets (cycles) |",
        "|---:|---|---:|---:|---|---|"
    ])

    for item in failures[:30]:
        lines.append(
            f"| ±{item['amplitude_cycles']} | {item['payload']} "
            f"| {item['trial']} | {item['seed']} "
            f"| {item['classification']} "
            f"| `{item['symbol_offsets_cycles']}` |"
        )

    lines.extend([
        "",
        "Every case uses independent deterministic duration perturbations per symbol. "
        "Results are empirical for this UART receiver and the chosen seeds, not a universal tolerance guarantee.",
        "",
        f"Production RTL SHA-256: `{report['source_hashes']['production_rtl_sha256']}`",
        ""
    ])
    md_path.write_text("\n".join(lines) + "\n")

    print(f"Jitter stress completed: {len(results)} cases")
    print("SUMMARY:", json.dumps(report["summary"], sort_keys=True))
    for item in by_amplitude:
        print(f"±{item['amplitude_cycles']} cycles:", item["counts"])
    print("FIRST NON-CORRECT CASES:")
    for item in failures[:8]:
        print(
            f"amplitude=±{item['amplitude_cycles']} "
            f"payload={item['payload']} trial={item['trial']} "
            f"seed={item['seed']} class={item['classification']} "
            f"offsets={item['symbol_offsets_cycles']}"
        )
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")

    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
