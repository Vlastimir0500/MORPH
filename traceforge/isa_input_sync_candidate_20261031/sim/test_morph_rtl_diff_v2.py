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
from morph_contract_v2 import run_contract


class RTLComparisonV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("verilator") is None:
            raise unittest.SkipTest("Verilator is not installed")

        cls.build_dir = ROOT / "build" / "obj_dir_uart_right_20261031"
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
        initial_pin = pins[0] if pins else 0
        model.step(pin_in=initial_pin, program_mode=True)
        model.step(pin_in=initial_pin, program_mode=True)
        expected = [model.step(rst_n=False, pin_in=initial_pin)]
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
                int(fields[12], 16),
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
                snapshot.rx_shift_reg,
            )
            self.assertEqual(got, want, f"Mismatch at trace index {index}\nRTL={got}\nModel={want}")

        return model

    def test_receive_register_shift_clear_and_commit(self):
        source = (
            "LOAD_IMM 0x5A\n"
            + "SAMPLE_SHIFT 1\n" * 8
            + "RX_CLEAR\n"
            + "SAMPLE_SHIFT 1\n" * 8
            + "RX_COMMIT\n"
            + "HALT"
        )

        pins = [0] * 42

        for bit_index in range(8):
            pins[1 + 2 * bit_index] = 0x02

        expected_byte = 0xA6
        for bit_index in range(8):
            bit = (expected_byte >> (7 - bit_index)) & 1
            pins[19 + 2 * bit_index] = bit << 1

        model = self.run_diff_words(assemble(source), pins)

        self.assertEqual(model.rx_shift_reg, expected_byte)
        self.assertEqual(model.shift_reg, expected_byte)
        self.assertFalse(model.fault)
        self.assertEqual(model.state, "HALT")

    def test_uart_lsb_first_right_shift_matches_rtl(self):
        payload = 0xA6
        source = "LOAD_IMM 0\n" + "SAMPLE_SHIFT 1, RIGHT\n" * 8
        source += "RX_COMMIT\nHALT"
        pins = [0] * 26

        for bit_index in range(8):
            bit = (payload >> bit_index) & 1
            pins[1 + 2 * bit_index] = bit << 1

        model = self.run_diff_words(assemble(source), pins)
        self.assertEqual(model.rx_shift_reg, payload)
        self.assertEqual(model.shift_reg, payload)
        self.assertFalse(model.fault)
        self.assertEqual(model.state, "HALT")

    def test_invalid_receive_instruction_encodings_match_rtl(self):
        invalid_words = (0xD002, 0xD800, 0xE001, 0xF001)

        for word in invalid_words:
            with self.subTest(instruction=f"0x{word:04X}"):
                self.run_diff_words([0x1101, word], [0] * 20)

    def test_contract_generated_scenarios_match_rtl(self):
        contract_path = ROOT / "protocols" / "v2_edge_timed_release.contract.json"
        report_path = ROOT / "build" / "v2_edge_timed_release.model-conformance-report.json"
        report, _ = run_contract(contract_path, report_path)
        self.assertEqual(report["status"], "PASS")
        words = [int(word, 16) for word in report["words_hex"]]
        for scenario in report["scenarios"]:
            with self.subTest(scenario=scenario["name"]):
                self.run_diff_words(words, scenario["pin_trace"])

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


    def test_load_immediate_and_open_drain_shift(self):
        source = "LOAD_IMM 0xA5\nOD_SHIFT 0\nOD_SHIFT 1\nLOAD_IMM 0xA5\nDRIVE_SHIFT 2\nDRIVE_SHIFT 3\nHALT"
        self.run_diff_words(assemble(source), [0] * 32)


if __name__ == "__main__":
    unittest.main()
