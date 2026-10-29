import inspect
import importlib.util
import os
from pathlib import Path

root = Path(os.environ["RUN_DIR"])
source = root / "morph_isa_model_v2_vote3.py"

spec = importlib.util.spec_from_file_location("edge_capture_model", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

model = module.MorphISAModelV2()
model.load_program([0xB001, 0x6000])

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
    raise SystemExit("MODEL FAIL: first rising edge was not captured")

for period in (430, 463, 407):
    for offset in range(1, period + 1):
        pin_value = 0 if period // 2 <= offset < period else 1
        tick(pin_value)

    if not model.edge_capture_valid:
        raise SystemExit("MODEL FAIL: capture validity was not asserted")

    if model.edge_interval != period:
        raise SystemExit(
            f"MODEL FAIL: expected {period}, got {model.edge_interval}"
        )

    print(f"MODEL PASS: measured interval {model.edge_interval} cycles")

if model.fault:
    raise SystemExit("MODEL FAIL: unexpected fault")

print("EDGE_CAPTURE REFERENCE MODEL TEST PASS")
