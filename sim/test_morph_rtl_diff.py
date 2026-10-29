import random
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sim"))
sys.path.insert(0, str(ROOT / "compiler"))

from morph_assembler import assemble
from morph_isa_model import MorphISAModel


STATE_CODES = {
    "FETCH": 0,
    "EXEC": 1,
    "WAIT": 2,
    "EDGE_WAIT": 3,
}


class RTLComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_dir = ROOT / "build" / "obj_dir_morph_diff"
        shutil.rmtree(cls.build_dir, ignore_errors=True)

        command = [
            "verilator",
            "--binary",
            "--timing",
            "-Wno-fatal",
            "--top-module",
            "morph_engine_diff_tb",
            "--Mdir",
            str(cls.build_dir),
            str(ROOT / "rtl" / "morph_engine.sv"),
            str(ROOT / "sim" / "morph_engine_diff_tb.sv"),
        ]

        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stdout + "\n" + result.stderr)

        cls.executable = cls.build_dir / "Vmorph_engine_diff_tb"

    def test_python_model_matches_rtl_every_cycle(self):
        source = (ROOT / "protocols" / "edge_timed_release.morph").read_text()
        words = assemble(source)

        program_path = ROOT / "build" / "rtl_diff_program.hex"
        program = words + [0] * (16 - len(words))
        program_path.write_text(
            "".join(f"{word:04x}\n" for word in program)
        )

        rng = random.Random(20261011)
        pins = [
            0, 0, 1, 1, 1, 0, 0, 1,
            0, 1, 1, 0, 0, 0, 1, 1,
        ]
        pins.extend(rng.randrange(2) for _ in range(80))

        vectors = [0] + [0b10 | pin for pin in pins]
        vector_path = ROOT / "build" / "rtl_diff_vectors.hex"
        vector_path.write_text(
            "".join(f"{vector:x}\n" for vector in vectors)
        )

        model = MorphISAModel()
        model.load_program(words)
        expected_trace = model.run(pins)

        result = subprocess.run(
            [str(self.executable), f"+N={len(vectors)}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stdout + "\n" + result.stderr,
        )

        actual_trace = []
        for line in result.stdout.splitlines():
            if not line.startswith("TRACE "):
                continue

            fields = line.split()
            actual_trace.append(
                (
                    int(fields[2]),
                    int(fields[3]),
                    int(fields[4], 16),
                    int(fields[5]),
                    int(fields[6]),
                    int(fields[7], 16),
                    int(fields[8]),
                )
            )

        self.assertEqual(
            len(actual_trace),
            len(expected_trace),
            msg="RTL trace length differs from Python trace",
        )

        for index, (actual, expected) in enumerate(
            zip(actual_trace, expected_trace)
        ):
            expected_values = (
                STATE_CODES[expected.state],
                expected.pc,
                expected.instruction,
                expected.pin_out,
                expected.sample_reg,
                expected.shift_reg,
                expected.wait_count,
            )

            if actual != expected_values:
                self.fail(
                    f"First mismatch at cycle index {index}\n"
                    f"RTL:    {actual}\n"
                    f"Python: {expected_values}"
                )

        print(
            f"PASS: RTL matches Python model for "
            f"{len(actual_trace)} cycles"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
