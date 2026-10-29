import hashlib
import json
import os
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ["MORPH_ROOT"]).resolve()
RUN_DIR = Path(os.environ["MORPH_RUN_DIR"]).resolve()
REPORT_DIR = ROOT / "traceforge" / "reports"
RTL = ROOT / "rtl" / "morph_engine_v2.sv"
TT_RTL = ROOT / "tinytapeout-template-v2" / "src" / "morph_engine.sv"
FIRMWARE = ROOT / "protocols" / "v2_uart_rx_a6.hex"
SOURCE_TB = ROOT / "traceforge" / "rtl_run" / "morph_engine_v2_traceforge_tb.sv"

sys.path.insert(0, str(ROOT / "traceforge" / "rtl_run"))
sys.path.insert(0, str(ROOT / "sim"))
from traceforge_uart_rtl import expected_snapshot, parse_trace
from morph_isa_model_v2 import MorphISAModelV2

PAYLOADS = [0x00, 0xFF, 0x55, 0x3C, 0x81, 0x7E, 0xA5, 0xA6]
PERIODS = list(range(400, 471))
WAITS = [214, 215]
NOMINAL = 436
IDLE = 10
TAIL = 240
JITTER_AMPLITUDES = [20, 40, 60, 80]
JITTER_PER_AMPLITUDE = 150
JITTER_SEED = 20261101
BOUNDARY_DELTAS = list(range(-220, -207))
MINIMIZED_DURATIONS = [427, 436, 421, 379, 436, 400, 396, 377, 436, 436]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reverse_byte(value):
    result = 0
    for bit in range(8):
        result = (result << 1) | ((value >> bit) & 1)
    return result


def compress_ranges(values):
    values = sorted(set(values))
    if not values:
        return []
    result = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
        else:
            result.append([start, previous])
            start = previous = value
    result.append([start, previous])
    return result


def build_uniform(payload, period):
    pins = [1] * IDLE + [0] * period
    for bit in range(8):
        pins.extend([((payload >> bit) & 1)] * period)
    pins.extend([1] * period)
    pins.extend([1] * TAIL)
    return pins


def build_jittered(payload, durations):
    pins = [1] * IDLE + [0] * durations[0]
    for bit in range(8):
        pins.extend([((payload >> bit) & 1)] * durations[bit + 1])
    pins.extend([1] * durations[9])
    pins.extend([1] * TAIL)
    return pins


def build_bad_start():
    return [1] * IDLE + [0] * 12 + [1] * (NOMINAL * 10 + TAIL)


def build_bad_stop(payload):
    pins = [1] * IDLE + [0] * NOMINAL
    for bit in range(8):
        pins.extend([((payload >> bit) & 1)] * NOMINAL)
    pins.extend([0] * NOMINAL)
    pins.extend([1] * TAIL)
    return pins


def build_aggregate_low_run(delta):
    return [1] * IDLE + [0] * (9 * NOMINAL + delta) + [1] * NOMINAL + [1] * TAIL


def make_specs():
    specs = []

    for payload in PAYLOADS:
        for period in PERIODS:
            specs.append({
                "case": f"matrix_{payload:02X}_period_{period}",
                "category": "uniform_period_matrix",
                "payload": payload,
                "pins": build_uniform(payload, period),
                "details": {"bit_period_cycles": period},
                "malformed": False
            })

    rng = random.Random(JITTER_SEED)
    for amplitude in JITTER_AMPLITUDES:
        for trial in range(JITTER_PER_AMPLITUDE):
            payload = rng.choice(PAYLOADS)
            durations = [
                NOMINAL + rng.randint(-amplitude, amplitude)
                for _ in range(10)
            ]
            specs.append({
                "case": f"jitter_{amplitude}_{trial:03d}",
                "category": "randomized_symbol_jitter",
                "payload": payload,
                "pins": build_jittered(payload, durations),
                "details": {
                    "jitter_amplitude_cycles": amplitude,
                    "trial": trial,
                    "random_seed": JITTER_SEED,
                    "symbol_durations_cycles": durations
                },
                "malformed": False
            })

    specs.extend([
        {
            "case": "malformed_short_start_glitch",
            "category": "malformed_frame",
            "payload": 0x00,
            "pins": build_bad_start(),
            "details": {"malformation": "12-cycle start glitch"},
            "malformed": True
        },
        {
            "case": "malformed_low_stop",
            "category": "malformed_frame",
            "payload": 0xA6,
            "pins": build_bad_stop(0xA6),
            "details": {"malformation": "stop symbol held low"},
            "malformed": True
        },
        {
            "case": "minimized_counterexample_payload00",
            "category": "minimized_counterexample",
            "payload": 0x00,
            "pins": build_jittered(0x00, MINIMIZED_DURATIONS),
            "details": {
                "symbol_durations_cycles": MINIMIZED_DURATIONS,
                "minimizer_seed": 26261051
            },
            "malformed": False
        }
    ])

    for delta in BOUNDARY_DELTAS:
        specs.append({
            "case": f"aggregate_low_run_delta_{delta:+d}",
            "category": "aggregate_low_run_boundary",
            "payload": 0x00,
            "pins": build_aggregate_low_run(delta),
            "details": {"aggregate_low_run_delta_cycles": delta},
            "malformed": False
        })

    if len(specs) != 1184:
        raise RuntimeError(f"Unexpected spec count: {len(specs)}")

    return specs


def prepare_simulator():
    tb_text = SOURCE_TB.read_text()
    relative = RUN_DIR.relative_to(ROOT).as_posix()

    replacements = {
        "traceforge/rtl_run/morph_v2_program.hex":
            f"{relative}/morph_v2_program.hex",
        "traceforge/rtl_run/morph_v2_vectors.hex":
            f"{relative}/morph_v2_vectors.hex"
    }

    for old, new in replacements.items():
        if old not in tb_text:
            raise RuntimeError(f"Expected testbench reference missing: {old}")
        tb_text = tb_text.replace(old, new)

    tb_copy = RUN_DIR / "morph_engine_v2_phase_sweep_tb.sv"
    tb_copy.write_text(tb_text)

    build_dir = RUN_DIR / "obj_dir"
    command = [
        "verilator", "--binary", "--timing", "-Wno-fatal",
        "--top-module", "morph_engine_v2_diff_tb",
        "--Mdir", str(build_dir), str(RTL), str(tb_copy)
    ]

    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=240
    )
    (RUN_DIR / "verilator_build.log").write_text(
        result.stdout + "\n" + result.stderr
    )

    if result.returncode:
        raise RuntimeError("Verilator build failed; see verilator_build.log")

    return build_dir / "Vmorph_engine_v2_diff_tb"


def simulate(executable, program_path, vectors_path, program, spec, wait_value):
    padded = program + [0] * (64 - len(program))
    program_path.write_text("".join(f"{word:04x}\n" for word in padded))
    vectors_path.write_text("".join(f"{pin:02x}\n" for pin in spec["pins"]))

    model = MorphISAModelV2()
    model.load_program(program)
    expected = [expected_snapshot(model.step(rst_n=False, pin_in=0))]
    expected.extend(
        expected_snapshot(model.step(pin_in=pin))
        for pin in spec["pins"]
    )

    run = subprocess.run(
        [str(executable), f"+N={len(spec['pins'])}"],
        cwd=ROOT, capture_output=True, text=True, timeout=120
    )

    if run.returncode:
        raise RuntimeError(
            f"Simulation failed at {spec['case']} / WAIT={wait_value}\n"
            f"{run.stdout[-1500:]}\n{run.stderr[-1500:]}"
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
        for cycle, (got, want) in enumerate(zip(actual, expected)):
            if got != want:
                mismatch = {
                    "kind": "cycle_mismatch",
                    "cycle": cycle,
                    "rtl": list(got),
                    "model": list(want)
                }
                break

    if not actual:
        raise RuntimeError(f"Empty RTL trace for {spec['case']}")

    final = actual[-1]
    pin_out, pin_oe, observed = final[3], final[4], final[6]
    error_flag = bool((pin_out & pin_oe) & 0x80)
    core_fault = bool(final[9])
    expected_shift = reverse_byte(spec["payload"])

    if mismatch:
        classification = "rtl_model_mismatch"
    elif core_fault:
        classification = "core_fault"
    elif spec["malformed"]:
        classification = "malformed_rejected" if error_flag else "malformed_silent_acceptance"
    elif error_flag:
        classification = "error_flagged"
    elif observed != expected_shift:
        classification = "silent_misdecode"
    else:
        classification = "correct_decode"

    return {
        "case": spec["case"],
        "category": spec["category"],
        "payload": f"0x{spec['payload']:02X}",
        "wait_value": wait_value,
        "expected_shift": f"0x{expected_shift:02X}",
        "observed_shift": f"0x{observed:02X}",
        "error_flag": error_flag,
        "core_fault": core_fault,
        "rtl_model_match": mismatch is None,
        "first_mismatch": mismatch,
        "classification": classification,
        **spec["details"]
    }


def summarize(rows):
    by_category = {}
    for category in sorted({row["category"] for row in rows}):
        selected = [row for row in rows if row["category"] == category]
        by_category[category] = dict(sorted(Counter(
            row["classification"] for row in selected
        ).items()))

    matrix = [r for r in rows if r["category"] == "uniform_period_matrix"]
    jitter = [r for r in rows if r["category"] == "randomized_symbol_jitter"]
    malformed = [r for r in rows if r["category"] == "malformed_frame"]

    per_payload = {}
    for payload in PAYLOADS:
        selected = [r for r in matrix if r["payload"] == f"0x{payload:02X}"]
        good_periods = [
            r["bit_period_cycles"] for r in selected
            if r["classification"] == "correct_decode"
        ]
        per_payload[f"0x{payload:02X}"] = {
            "classification_counts": dict(sorted(Counter(
                r["classification"] for r in selected
            ).items())),
            "correct_period_ranges": compress_ranges(good_periods)
        }

    common_periods = []
    for period in PERIODS:
        selected = [
            r for r in matrix if r["bit_period_cycles"] == period
        ]
        if len(selected) == len(PAYLOADS) and all(
            r["classification"] == "correct_decode" for r in selected
        ):
            common_periods.append(period)

    jitter_by_amplitude = {}
    for amplitude in JITTER_AMPLITUDES:
        selected = [
            r for r in jitter
            if r["jitter_amplitude_cycles"] == amplitude
        ]
        jitter_by_amplitude[str(amplitude)] = dict(sorted(Counter(
            r["classification"] for r in selected
        ).items()))

    return {
        "cases": len(rows),
        "classification_counts_all": dict(sorted(Counter(
            r["classification"] for r in rows
        ).items())),
        "rtl_model_mismatches": sum(not r["rtl_model_match"] for r in rows),
        "by_category": by_category,
        "matrix": {
            "cases": len(matrix),
            "classification_counts": dict(sorted(Counter(
                r["classification"] for r in matrix
            ).items())),
            "common_correct_period_ranges": compress_ranges(common_periods),
            "per_payload": per_payload
        },
        "jitter": {
            "cases": len(jitter),
            "classification_counts": dict(sorted(Counter(
                r["classification"] for r in jitter
            ).items())),
            "by_amplitude": jitter_by_amplitude
        },
        "malformed": {
            "cases": len(malformed),
            "classification_counts": dict(sorted(Counter(
                r["classification"] for r in malformed
            ).items())),
            "both_rejected": len(malformed) == 2 and all(
                r["classification"] == "malformed_rejected"
                for r in malformed
            )
        },
        "minimized_counterexample": [
            {
                "classification": r["classification"],
                "observed_shift": r["observed_shift"]
            }
            for r in rows if r["category"] == "minimized_counterexample"
        ],
        "boundary": [
            {
                "delta": r["aggregate_low_run_delta_cycles"],
                "classification": r["classification"]
            }
            for r in rows if r["category"] == "aggregate_low_run_boundary"
        ]
    }


def main():
    sources_before = {
        "production_rtl_sha256": sha256(RTL),
        "tinytapeout_rtl_sha256": sha256(TT_RTL),
        "production_firmware_sha256": sha256(FIRMWARE),
        "source_testbench_sha256": sha256(SOURCE_TB)
    }

    if sources_before["production_rtl_sha256"] != sources_before["tinytapeout_rtl_sha256"]:
        raise RuntimeError("Production RTL and TinyTapeout RTL differ")

    baseline_program = [
        int(line.strip(), 16)
        for line in FIRMWARE.read_text().splitlines()
        if line.strip()
    ]

    if len(baseline_program) != 18 or baseline_program[4] != 0x30D7 or baseline_program[5] != 0x30D7:
        raise RuntimeError("Production firmware differs from expected baseline")

    executable = prepare_simulator()
    program_path = RUN_DIR / "morph_v2_program.hex"
    vectors_path = RUN_DIR / "morph_v2_vectors.hex"
    specs = make_specs()

    all_rows = {}
    summaries = {}
    variants = []

    for wait in WAITS:
        program = baseline_program.copy()
        program[4] = 0x3000 | wait
        program[5] = 0x3000 | wait
        phase_shift = 2 * (wait - 215)
        name = f"wait_{wait}_phase_{phase_shift:+d}"
        variants.append({
            "name": name,
            "wait_value": wait,
            "phase_shift_cycles": phase_shift
        })

    print("===== TRACEFORGE UART PHASE SWEEP v0.1 =====", flush=True)
    print(f"Run directory: {RUN_DIR}", flush=True)
    print(f"Settings: {[v['phase_shift_cycles'] for v in variants]} cycles", flush=True)
    print(f"Cases per setting: {len(specs)}", flush=True)
    print(f"Total simulations: {len(specs) * len(variants)}", flush=True)
    print("Production RTL and firmware remain unchanged.", flush=True)

    for variant in variants:
        program = baseline_program.copy()
        wait = variant["wait_value"]
        program[4] = 0x3000 | wait
        program[5] = 0x3000 | wait
        rows = []

        print(
            f"Starting phase {variant['phase_shift_cycles']:+d}, WAIT={wait}",
            flush=True
        )

        for index, spec in enumerate(specs, start=1):
            rows.append(
                simulate(executable, program_path, vectors_path, program, spec, wait)
            )
            if index % 100 == 0 or index == len(specs):
                print(
                    f"Phase {variant['phase_shift_cycles']:+d}: {index}/{len(specs)} "
                    f"simulations",
                    flush=True
                )

        all_rows[variant["name"]] = rows
        summaries[variant["name"]] = summarize(rows)

    baseline_variant = next(v for v in variants if v["wait_value"] == 215)
    baseline_rows = {
        r["case"]: r for r in all_rows[baseline_variant["name"]]
    }
    paired_deltas = {}

    for variant in variants:
        if variant["wait_value"] == 215:
            continue

        rows = all_rows[variant["name"]]
        transitions = Counter()
        improvements = []
        regressions = []

        for row in rows:
            base = baseline_rows[row["case"]]
            transitions[(base["classification"], row["classification"])] += 1

            if base["classification"] != "correct_decode" and row["classification"] == "correct_decode":
                improvements.append(row["case"])

            if base["classification"] == "correct_decode" and row["classification"] != "correct_decode":
                regressions.append(row["case"])

        base_counts = Counter(r["classification"] for r in baseline_rows.values())
        test_counts = Counter(r["classification"] for r in rows)

        paired_deltas[variant["name"]] = {
            "phase_shift_cycles": variant["phase_shift_cycles"],
            "correct_decode_delta": test_counts["correct_decode"] - base_counts["correct_decode"],
            "silent_misdecode_delta": test_counts["silent_misdecode"] - base_counts["silent_misdecode"],
            "error_flagged_delta": test_counts["error_flagged"] - base_counts["error_flagged"],
            "improved_cases": len(improvements),
            "regressed_cases": len(regressions),
            "improvement_case_names": improvements,
            "regression_case_names": regressions,
            "classification_transitions": [
                {
                    "baseline": a,
                    "setting": b,
                    "count": n
                }
                for (a, b), n in sorted(transitions.items())
            ]
        }

    sources_after = {
        "production_rtl_sha256": sha256(RTL),
        "tinytapeout_rtl_sha256": sha256(TT_RTL),
        "production_firmware_sha256": sha256(FIRMWARE),
        "source_testbench_sha256": sha256(SOURCE_TB)
    }

    sources_unchanged = sources_before == sources_after
    no_model_mismatches = all(
        summary["rtl_model_mismatches"] == 0
        for summary in summaries.values()
    )
    malformed_checks_pass = all(
        summary["malformed"]["both_rejected"]
        for summary in summaries.values()
    )

    gate_pass = sources_unchanged and no_model_mismatches and malformed_checks_pass

    report = {
        "experiment": "Identical UART RX test vectors across seven isolated sample-phase settings",
        "phase_settings": variants,
        "cases_per_setting": len(specs),
        "total_simulations": len(specs) * len(variants),
        "jitter_seed": JITTER_SEED,
        "sources_before": sources_before,
        "sources_after": sources_after,
        "production_sources_unchanged": sources_unchanged,
        "execution_gate_status": "PASS" if gate_pass else "FAIL",
        "summaries": summaries,
        "paired_deltas_vs_wait_215": paired_deltas,
        "all_case_results": all_rows,
        "promotion_recommendation": "HOLD_FOR_REVIEW: select no production firmware setting automatically; review common timing ranges, regressions, jitter results, and the existing release gate."
    }

    report_json = REPORT_DIR / f"{RUN_DIR.name}.json"
    report_md = REPORT_DIR / f"{RUN_DIR.name}.md"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# TRACEFORGE UART Phase Sweep v0.1",
        "",
        f"- Execution gate: **{report['execution_gate_status']}**",
        f"- Total simulations: {report['total_simulations']}",
        f"- Production sources unchanged: {sources_unchanged}",
        f"- RTL/reference mismatches: zero = {no_model_mismatches}",
        "",
        "| Phase shift | WAIT value | Correct matrix | Silent matrix | Flagged matrix | Common correct period range | Jitter correct | Jitter silent | Counterexample |",
        "|---:|---:|---:|---:|---:|---|---:|---:|---|"
    ]

    for variant in variants:
        summary = summaries[variant["name"]]
        mc = summary["matrix"]["classification_counts"]
        jc = summary["jitter"]["classification_counts"]
        ce = summary["minimized_counterexample"]
        lines.append(
            f"| {variant['phase_shift_cycles']:+d} | {variant['wait_value']} | "
            f"{mc.get('correct_decode', 0)} | {mc.get('silent_misdecode', 0)} | "
            f"{mc.get('error_flagged', 0)} | "
            f"{summary['matrix']['common_correct_period_ranges']} | "
            f"{jc.get('correct_decode', 0)} | {jc.get('silent_misdecode', 0)} | "
            f"{ce} |"
        )

    lines.extend([
        "",
        "## Paired deltas against baseline WAIT=215",
        "",
        "| Phase shift | Correct delta | Silent misdecode delta | Flagged error delta | Improved cases | Regressed cases |",
        "|---:|---:|---:|---:|---:|---:|"
    ])

    for name, delta in paired_deltas.items():
        lines.append(
            f"| {delta['phase_shift_cycles']:+d} | "
            f"{delta['correct_decode_delta']:+d} | "
            f"{delta['silent_misdecode_delta']:+d} | "
            f"{delta['error_flagged_delta']:+d} | "
            f"{delta['improved_cases']} | {delta['regressed_cases']} |"
        )

    lines.extend([
        "",
        "## Decision",
        "",
        report["promotion_recommendation"],
        "",
        f"Production RTL SHA-256: `{sources_after['production_rtl_sha256']}`",
        f"Production firmware SHA-256: `{sources_after['production_firmware_sha256']}`",
        ""
    ])
    report_md.write_text("\n".join(lines))

    print("===== PHASE SWEEP SUMMARY =====", flush=True)
    print("shift | WAIT | matrix correct | silent | flagged | common range | jitter correct | jitter silent", flush=True)

    for variant in variants:
        summary = summaries[variant["name"]]
        mc = summary["matrix"]["classification_counts"]
        jc = summary["jitter"]["classification_counts"]
        print(
            f"{variant['phase_shift_cycles']:+5d} | {variant['wait_value']:4d} | "
            f"{mc.get('correct_decode', 0):14d} | "
            f"{mc.get('silent_misdecode', 0):6d} | "
            f"{mc.get('error_flagged', 0):7d} | "
            f"{summary['matrix']['common_correct_period_ranges']} | "
            f"{jc.get('correct_decode', 0):14d} | "
            f"{jc.get('silent_misdecode', 0):12d}",
            flush=True
        )

    print("===== PAIRED DELTAS VS WAIT=215 =====", flush=True)
    print(json.dumps(paired_deltas, indent=2), flush=True)
    print(f"EXECUTION GATE: {report['execution_gate_status']}", flush=True)
    print(f"JSON REPORT: {report_json}", flush=True)
    print(f"MARKDOWN REPORT: {report_md}", flush=True)
    print(f"PRODUCTION RTL SHA256 AFTER: {sources_after['production_rtl_sha256']}", flush=True)

    if not gate_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
