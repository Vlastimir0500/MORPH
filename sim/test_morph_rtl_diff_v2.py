import random
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compiler"))
sys.path.insert(0, str(ROOT / "sim"))

from morph_assembler_v2 import assemble
from morph_isa_model_v2 import MorphISAModelV2, STATE_CODES


class RTLComparisonV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("verilator") is None:
            raise unittest.SkipTest("Verilator is not installed")

        cls.build_dir = ROOT / "build" / "obj_dir_morph_v2_diff"
        shutil.rmtree(cls.build_dir, ignore_errors=True)
        command = [
            "verilator", "--binary", "--timing", "-Wno-fatal",
            "--top-module", "morph_engine_v2_diff_tb",
            "--Mdir", str(cls.build_dir),
            str(ROOT / "rtl" / "morph_engine_v2.sv"),
            str(ROOT / "sim" / "morph_engine_v2_diff_tb.sv"),
        ]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            raise RuntimeError(result.stdout + "\n" + result.stderr)
        cls.executable = cls.build_dir / "Vmorph_engine_v2_diff_tb"

    def run_diff_words(self, words, pins):
        if len(words) > 64:
            self.fail("test program exceeds the V2 program memory")

        program_path = ROOT / "build" / "morph_v2_program.hex"
        vectors_path = ROOT / "build" / "morph_v2_vectors.hex"
        program_path.write_text("".join(f"{word:04x}\n" for word in words + [0] * (64 - len(words))))
        vectors_path.write_text("".join(f"{pin:02x}\n" for pin in pins))

        model = MorphISAModelV2()
        model.load_program(words)
        expected = [model.step(rst_n=False, pin_in=0)]
        expected.extend(model.step(pin_in=pin) for pin in pins)

        result = subprocess.run(
            [str(self.executable), f"+N={len(pins)}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + "\n" + result.stderr)

        actual = []
        for line in result.stdout.splitlines():
            if not line.startswith("TRACE "):
                continue
            fields = line.split()
            actual.append((
                int(fields[2]),
                int(fields[3]),
                int(fields[4], 16),
                int(fields[5], 16),
                int(fields[6], 16),
                int(fields[7]),
                int(fields[8], 16),
                int(fields[9]),
                int(fields[10]),
                int(fields[11]),
            ))

        self.assertEqual(len(actual), len(expected), result.stdout)
        for index, (got, snapshot) in enumerate(zip(actual, expected)):
            want = (
                STATE_CODES[snapshot.state],
                snapshot.pc,
                snapshot.instruction,
                snapshot.pin_out,
                snapshot.pin_oe,
                snapshot.sample_reg,
                snapshot.shift_reg,
                snapshot.wait_count,
                int(snapshot.timed_out),
                int(snapshot.fault),
            )
            self.assertEqual(got, want, f"Mismatch at trace index {index}\nRTL={got}\nModel={want}")

    def test_drive_wait_release_halt(self):
        self.run_diff_words(assemble("DRIVE 3, 1\nWAIT 2\nRELEASE 3\nHALT"), [0] * 32)

    def test_sample_shift(self):
        self.run_diff_words(assemble("SAMPLE 5\nSHIFT\nHALT"), [0x20] * 24)

    def test_bounded_rising_edge(self):
        pins = [0, 0, 0, 0x04, 0x04, 0x04] + [0x04] * 24
        self.run_diff_words(assemble("EDGE 2, RISE, 7\nDRIVE 4, 1\nHALT"), pins)

    def test_bounded_falling_edge_timeout(self):
        self.run_diff_words(assemble("EDGE 1, FALL, 4\nDRIVE 6, 1\nHALT"), [0] * 32)

    def test_conditional_branch_taken(self):
        source = "SAMPLE 5\nBRANCH_SAMPLE 1, yes\nDRIVE 1, 1\nyes: DRIVE 2, 1\nHALT"
        self.run_diff_words(assemble(source), [0x20] * 32)

    def test_conditional_branch_not_taken(self):
        source = "SAMPLE 5\nBRANCH_SAMPLE 1, yes\nDRIVE 1, 1\nyes: DRIVE 2, 1\nHALT"
        self.run_diff_words(assemble(source), [0] * 32)

    def test_counted_loop_three_passes(self):
        source = "start: SAMPLE 0\nSHIFT\nLOOP 3, start\nHALT"
        self.run_diff_words(assemble(source), [0x01] * 40)

    def test_counted_loop_single_pass(self):
        source = "start: SAMPLE 0\nSHIFT\nLOOP 1, start\nHALT"
        self.run_diff_words(assemble(source), [0x01] * 28)

    def test_counted_loop_maximum_count(self):
        source = "start: DRIVE 0, 1\nDRIVE 0, 0\nLOOP 63, start\nHALT"
        self.run_diff_words(assemble(source), [0] * 420)

    def test_nested_counted_loop_fails_safe(self):
        source = "outer: DRIVE 0, 1\ninner: DRIVE 1, 1\nLOOP 2, inner\nLOOP 2, outer\nHALT"
        self.run_diff_words(assemble(source), [0] * 50)

    def test_counted_loop_boundary_counts(self):
        for count in (1, 2, 3, 7, 31, 63):
            with self.subTest(count=count):
                source = f"start: SAMPLE 0\nSHIFT\nLOOP {count}, start\nHALT"
                rng = random.Random(20261028 + count)
                pins = [rng.randrange(2) for _ in range(420)]
                self.run_diff_words(assemble(source), pins)

    def test_malformed_counted_loop_fault_paths(self):
        invalid_programs = (
            [0x1101, 0x9000],
            [0x1101, 0x9041],
        )
        for words in invalid_programs:
            with self.subTest(words=words):
                self.run_diff_words(words, [0] * 24)

    def test_invalid_opcode_fault_path(self):
        self.run_diff_words([0x1101, 0xA000], [0] * 20)

    def test_invalid_pin_fault_path(self):
        self.run_diff_words([0x1101, 0x1801], [0] * 20)

    def test_randomized_input_sequence(self):
        rng = random.Random(20261027)
        source = "DRIVE 0, 1\nSAMPLE 5\nSHIFT\nEDGE 2, RISE, 13\nRELEASE 0\nHALT"
        pins = [rng.randrange(256) for _ in range(120)]
        self.run_diff_words(assemble(source), pins)


if __name__ == "__main__":
    unittest.main()
