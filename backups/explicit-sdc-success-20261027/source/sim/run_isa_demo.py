import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "compiler"))

from morph_assembler import assemble
from morph_isa_model import MorphISAModel


source = Path("protocols/edge_timed_release.morph").read_text()
words = assemble(source)

model = MorphISAModel()
model.load_program(words)

print("cycle state      pc instruction pin_out sample shift wait executed")

for snapshot in model.run([0, 0, 1] + [1] * 16):
    print(
        f"{snapshot.cycle:5} "
        f"{snapshot.state:10} "
        f"{snapshot.pc:2} "
        f"0x{snapshot.instruction:04X} "
        f"{snapshot.pin_out:7} "
        f"{snapshot.sample_reg:6} "
        f"{snapshot.shift_reg:5} "
        f"{snapshot.wait_count:4} "
        f"{snapshot.executed}"
    )
