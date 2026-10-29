import importlib.util
import inspect
import os
import sys
from pathlib import Path

root = Path(os.environ["RUN_DIR"])
spec = importlib.util.spec_from_file_location(
    "edge_wrap_model",
    root / "morph_isa_model_v2_vote3.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

model = module.MorphISAModelV2()
model.load_program([0xB002, 0x6000])
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

model.cycle = 65490
tick(1)

first_cycle_value = model.edge_last_cycle

if first_cycle_value + 430 < 65536:
    raise SystemExit("MODEL FAIL: rollover was not exercised")

for period, next_level in ((430, 0), (463, 1), (407, 0)):
    for offset in range(1, period + 1):
        tick(next_level if offset == period else 1 - next_level)

    if not model.edge_capture_valid:
        raise SystemExit("MODEL FAIL: interval was not marked valid")

    if model.edge_interval != period:
        raise SystemExit(
            f"MODEL FAIL: expected {period}, got {model.edge_interval}"
        )

    print(f"MODEL PASS: interval {model.edge_interval} cycles")

if model.fault:
    raise SystemExit("MODEL FAIL: unexpected fault")

print("EDGE CAPTURE ROLLOVER MODEL TEST PASS")
