import importlib.util
import inspect
import os
import sys
from pathlib import Path

root = Path(os.environ["RUN_DIR"])
spec = importlib.util.spec_from_file_location(
    "sample_compensation_model",
    root / "morph_isa_model_v2_vote3.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

periods = (10, 11, 20, 37, 101, 255, 350, 403, 407, 430, 463, 479, 520, 1023)
parameters = inspect.signature(module.MorphISAModelV2.step).parameters

def tick(model, pin_value):
    values = {}
    for parameter in parameters.values():
        name = parameter.name
        if name == "self":
            continue
        if name in ("pin_in", "pins"):
            values[name] = pin_value
        elif name in ("rst_n", "reset_n"):
            values[name] = True
        elif name in ("program_mode", "program_high_byte", "reset"):
            values[name] = False
        elif name in ("program_addr", "program_byte"):
            values[name] = 0
        elif parameter.default is inspect.Parameter.empty:
            raise RuntimeError(f"Unknown required step parameter: {name}")
    return model.step(**values)

for period in periods:
    model = module.MorphISAModelV2()
    model.load_program([0xB002, 0xC000, 0x2000, 0x0000])

    for _ in range(10):
        tick(model, 1)

    if model.state != "EDGE_WAIT":
        raise SystemExit(f"MODEL FAIL: capture did not start for {period}")

    tick(model, 0)

    if not model.edge_seen:
        raise SystemExit(f"MODEL FAIL: initial edge not captured for {period}")

    capture_cycle = None

    for offset in range(1, period + 1):
        snapshot = tick(model, 1 if offset == period else 0)
        if offset == period:
            capture_cycle = model.cycle

    if not model.edge_capture_valid:
        raise SystemExit(f"MODEL FAIL: interval not captured for {period}")

    if model.edge_interval != period:
        raise SystemExit(
            f"MODEL FAIL: expected interval {period}, got {model.edge_interval}"
        )

    sample_cycle = None

    for _ in range(period + 30):
        snapshot = tick(model, 1)
        if snapshot.executed == "SAMPLE":
            sample_cycle = model.cycle
            break

    if sample_cycle is None:
        raise SystemExit(f"MODEL FAIL: SAMPLE was not executed for {period}")

    expected_half = period // 2
    elapsed = sample_cycle - capture_cycle

    if elapsed != expected_half:
        raise SystemExit(
            f"MODEL FAIL: period {period}, expected offset {expected_half}, got {elapsed}"
        )

    if model.sample_reg != 1 or model.fault:
        raise SystemExit(f"MODEL FAIL: incorrect sample or fault for period {period}")

    print(f"MODEL PASS: period={period}, target={expected_half}, actual={elapsed}")

print("SAMPLE COMPENSATION MODEL TEST PASS: 14/14")
