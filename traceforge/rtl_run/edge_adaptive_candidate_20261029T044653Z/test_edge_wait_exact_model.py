import importlib.util
import inspect
import os
import sys
from pathlib import Path

root = Path(os.environ["RUN_DIR"])
spec = importlib.util.spec_from_file_location(
    "edge_wait_exact_model",
    root / "morph_isa_model_v2_vote3.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

def run_case(period):
    model = module.MorphISAModelV2()
    model.load_program([0xB002, 0xC000, 0x2000, 0x0000])
    parameters = inspect.signature(model.step).parameters

    def tick(pin_value):
        values = {}
        for parameter in parameters.values():
            name = parameter.name
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

    for _ in range(10):
        tick(0)

    tick(1)

    for offset in range(1, period + 1):
        tick(0 if offset == period else 1)

    if not model.edge_capture_valid:
        raise SystemExit(f"MODEL FAIL: interval was not captured for {period}")

    if model.edge_interval != period:
        raise SystemExit(
            f"MODEL FAIL: expected interval {period}, got {model.edge_interval}"
        )

    for _ in range(10):
        if model.state == "CAPTURED_WAIT":
            break
        tick(0)

    if model.state != "CAPTURED_WAIT":
        raise SystemExit(f"MODEL FAIL: dynamic wait did not start for {period}")

    expected = period // 2

    if model.captured_wait_count != expected:
        raise SystemExit(
            f"MODEL FAIL: expected initial wait {expected}, got {model.captured_wait_count}"
        )

    start_cycle = model.cycle

    while model.state == "CAPTURED_WAIT":
        tick(0)

    elapsed = model.cycle - start_cycle

    if elapsed != expected:
        raise SystemExit(
            f"MODEL FAIL: expected wait duration {expected}, got {elapsed}"
        )

    if model.fault:
        raise SystemExit(f"MODEL FAIL: unexpected fault for {period}")

    print(f"MODEL PASS: interval={period}, half_wait={expected}, elapsed={elapsed}")

for value in (430, 463, 407):
    run_case(value)

print("EXACT-CYCLE REFERENCE MODEL TEST PASS")
