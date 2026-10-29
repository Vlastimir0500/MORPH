import importlib.util
import inspect
import os
import sys
from pathlib import Path

root = Path(os.environ["RUN_DIR"])
spec = importlib.util.spec_from_file_location("edge_adaptive_model", root / "morph_isa_model_v2_vote3.py")
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
            elif name == "program_mode":
                values[name] = False
            elif name == "program_high_byte":
                values[name] = False
            elif name == "program_addr":
                values[name] = 0
            elif name == "program_byte":
                values[name] = 0
            elif name == "reset":
                values[name] = False
            elif parameter.default is inspect.Parameter.empty:
                raise RuntimeError(f"Unknown required step parameter: {name}")
        return model.step(**values)

    for _ in range(10):
        tick(0)

    tick(1)

    if not model.edge_seen:
        raise SystemExit("MODEL FAIL: first transition not captured")
    if model.edge_capture_valid:
        raise SystemExit("MODEL FAIL: interval valid before second transition")

    for offset in range(1, period + 1):
        tick(0 if offset == period else 1)

    if not model.edge_capture_valid:
        raise SystemExit("MODEL FAIL: interval validity not asserted")
    if model.edge_interval != period:
        raise SystemExit(f"MODEL FAIL: expected {period}, got {model.edge_interval}")

    for _ in range(10):
        if model.state == "CAPTURED_WAIT":
            break
        tick(0)

    if model.state != "CAPTURED_WAIT":
        raise SystemExit("MODEL FAIL: captured wait did not start")
    if model.captured_wait_count != period // 2:
        raise SystemExit(
            f"MODEL FAIL: expected half wait {period // 2}, got {model.captured_wait_count}"
        )

    for _ in range(period // 2 + 10):
        tick(0)

    if model.sample_reg != 0:
        raise SystemExit("MODEL FAIL: sample was not low")
    if model.fault:
        raise SystemExit("MODEL FAIL: unexpected fault")

    print(f"MODEL PASS: edge interval {period}, half wait {period // 2}")

for period in (430, 463, 407):
    run_case(period)

print("EDGE ADAPTIVE REFERENCE MODEL TEST PASS")
