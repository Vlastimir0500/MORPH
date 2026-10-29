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
RTL = RUN_DIR / "morph_engine_v2_vote3.sv"
TT_RTL = ROOT / "tinytapeout-template-v2" / "src" / "morph_engine.sv"
FIRMWARE = ROOT / "protocols" / "v2_uart_rx_a6.hex"
SOURCE_TB = ROOT / "traceforge" / "rtl_run" / "morph_engine_v2_traceforge_tb.sv"

sys.path.insert(0, str(ROOT / "traceforge" / "rtl_run"))
sys.path.insert(0, str(ROOT / "sim"))
sys.path.insert(0, str(RUN_DIR))
from traceforge_uart_rtl import expected_snapshot, parse_trace
from morph_isa_model_v2_vote3 import MorphISAModelV2

PAYLOADS = [0x00, 0xFF, 0x55, 0x3C, 0x81, 0x7E, 0xA5, 0xA6]
PERIODS = list(range(400, 471))
WAITS = [209, 211, 213, 215, 217, 219, 221]
NOMINAL = 436
IDLE = 10
TAIL = 240
JITTER_AMPLITUDES = [20, 40, 60, 80]
JITTER_PER_AMPLITUDE = 150
JITTER_SEED = 20261028
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
    program_file = RUN_DIR / "v2_uart_rx_vote3_candidate.hex"
    program = [
        int(line.strip(), 16)
        for line in program_file.read_text().splitlines()
        if line.strip()
    ]
    if not program or len(program) > 64:
        raise SystemExit(f"Invalid program length: {len(program)}")

    executable = prepare_simulator()
    program_path = RUN_DIR / "morph_v2_program.hex"
    vectors_path = RUN_DIR / "morph_v2_vectors.hex"
    specs = make_specs()
    selected = {}

    for spec in specs:
        name = spec["case"]
        category = spec.get("category", "")
        details = spec.get("details", {})
        payload = spec.get("payload")
        period = details.get("bit_period_cycles")

        if category == "uniform_period_matrix":
            if period == 436:
                selected[name] = spec
            elif period in (413, 460) and payload in (0x00, 0xA6):
                selected[name] = spec

        if category == "randomized_symbol_jitter":
            if details.get("trial") in (0, 50, 100, 149):
                selected[name] = spec

        if spec.get("malformed"):
            selected[name] = spec

        if "minimized_counterexample" in name:
            selected[name] = spec

        if name in {
            "aggregate_low_run_delta_-220",
            "aggregate_low_run_delta_-216",
            "aggregate_low_run_delta_-215",
            "aggregate_low_run_delta_-208",
        }:
            selected[name] = spec

    if len(selected) < 25:
        raise SystemExit(
            f"Too few smoke cases selected: {len(selected)}; inspect make_specs()"
        )

    rows = []
    print(f"Variant: vote3_candidate")
    print(f"RTL source: {RTL}")
    print(f"Program words: {len(program)}")
    print(f"Selected input traces: {len(selected)}")

    for index, spec in enumerate(selected.values(), start=1):
        row = simulate(
            executable, program_path, vectors_path, program, spec, 0
        )
        rows.append(row)
        if index % 10 == 0 or index == len(selected):
            print(f"Simulations: {index}/{len(selected)}", flush=True)

    mismatches = [
        row for row in rows
        if not row.get("rtl_model_match", False)
    ]
    nominal = [
        row for row in rows
        if row.get("category") == "uniform_period_matrix"
        and any(
            spec["case"] == row["case"]
            and spec.get("details", {}).get("bit_period_cycles") == 436
            for spec in selected.values()
        )
    ]
    report = {
        "variant": "vote3_candidate",
        "program_words": len(program),
        "cases": len(rows),
        "rtl_model_mismatches": len(mismatches),
        "nominal_period_cases": len(nominal),
        "nominal_period_correct": sum(
            row.get("classification") == "correct_decode"
            for row in nominal
        ),
        "malformed_cases": [
            {
                "case": row["case"],
                "classification": row.get("classification"),
            }
            for row in rows
            if any(
                spec["case"] == row["case"] and spec.get("malformed")
                for spec in selected.values()
            )
        ],
        "results": rows,
    }

    report_path = RUN_DIR / "paired_smoke_results.json"
    report_path.write_text(__import__("json").dumps(report, indent=2) + "\n")
    print(f"RTL/reference mismatches: {len(mismatches)}")
    print(
        f"Nominal 436-cycle cases correct: "
        f"{report['nominal_period_correct']}/{report['nominal_period_cases']}"
    )
    for row in rows:
        print(
            f"{row['case']}: {row.get('classification')} "
            f"observed={row.get('observed_shift')} "
            f"model_match={row.get('rtl_model_match')}"
        )
    print(f"JSON report: {report_path}")

if __name__ == "__main__":
    main()
