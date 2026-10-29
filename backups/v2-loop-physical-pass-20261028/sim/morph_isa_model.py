from dataclasses import dataclass


PROGRAM_DEPTH = 16
WORD_MASK = 0xFFFF


@dataclass(frozen=True)
class Snapshot:
    cycle: int
    state: str
    pc: int
    instruction: int
    pin_out: int
    sample_reg: int
    shift_reg: int
    wait_count: int
    executed: str


class MorphISAModel:
    def __init__(self):
        self.memory = [0] * PROGRAM_DEPTH
        self.cycle = 0
        self._reset_registers()

    def _reset_registers(self):
        self.pc = 0
        self.ir = 0
        self.wait_count = 0
        self.pin_prev = 0
        self.sample_reg = 0
        self.shift_reg = 0
        self.pin_out = 0
        self.state = "FETCH"

    def load_program(self, words):
        if len(words) > PROGRAM_DEPTH:
            raise ValueError("program exceeds 16 instruction words")

        checked = []
        for word in words:
            if not isinstance(word, int) or not 0 <= word <= WORD_MASK:
                raise ValueError("program words must be unsigned 16-bit integers")
            checked.append(word)

        self.memory = checked + [0] * (PROGRAM_DEPTH - len(checked))

    def step(self, pin_in=0, rst_n=True):
        if pin_in not in (0, 1):
            raise ValueError("pin_in must be 0 or 1")

        self.cycle += 1
        executed = "-"
        state_before = self.state

        if not rst_n:
            self._reset_registers()
            executed = "RESET"
        else:
            previous_pin = self.pin_prev
            self.pin_prev = pin_in

            if self.state == "FETCH":
                self.ir = self.memory[self.pc]
                self.state = "EXEC"

            elif self.state == "EXEC":
                opcode = (self.ir >> 12) & 0xF
                arg = self.ir & 0xFF

                if opcode == 0x1:
                    self.pin_out = self.ir & 1
                    self.pc = (self.pc + 1) & 0xF
                    self.state = "FETCH"
                    executed = "DRIVE"

                elif opcode == 0x2:
                    self.sample_reg = pin_in
                    self.pc = (self.pc + 1) & 0xF
                    self.state = "FETCH"
                    executed = "SAMPLE"

                elif opcode == 0x3:
                    if arg == 0:
                        self.pc = (self.pc + 1) & 0xF
                        self.state = "FETCH"
                    else:
                        self.wait_count = arg
                        self.state = "WAIT"
                    executed = "WAIT"

                elif opcode == 0x4:
                    self.state = "EDGE_WAIT"
                    executed = "EDGE"

                elif opcode == 0x5:
                    self.shift_reg = (
                        ((self.shift_reg << 1) | self.sample_reg) & 0xFF
                    )
                    self.pc = (self.pc + 1) & 0xF
                    self.state = "FETCH"
                    executed = "SHIFT"

                elif opcode == 0x6:
                    self.pc = self.ir & 0xF
                    self.state = "FETCH"
                    executed = "BRANCH"

                else:
                    self.pc = (self.pc + 1) & 0xF
                    self.state = "FETCH"
                    executed = "INVALID_NOP"

            elif self.state == "WAIT":
                if self.wait_count <= 1:
                    self.wait_count = 0
                    self.pc = (self.pc + 1) & 0xF
                    self.state = "FETCH"
                else:
                    self.wait_count -= 1
                executed = "WAIT_TICK"

            elif self.state == "EDGE_WAIT":
                rising = pin_in == 1 and previous_pin == 0
                falling = pin_in == 0 and previous_pin == 1

                if self.ir & 1:
                    if rising:
                        self.pc = (self.pc + 1) & 0xF
                        self.state = "FETCH"
                elif falling:
                    self.pc = (self.pc + 1) & 0xF
                    self.state = "FETCH"

                executed = "EDGE_WAIT"

            else:
                raise RuntimeError(f"unknown model state: {self.state}")

        return Snapshot(
            cycle=self.cycle,
            state=self.state,
            pc=self.pc,
            instruction=self.ir,
            pin_out=self.pin_out,
            sample_reg=self.sample_reg,
            shift_reg=self.shift_reg,
            wait_count=self.wait_count,
            executed=executed,
        )

    def run(self, pin_values, reset_first=True):
        trace = []

        if reset_first:
            trace.append(self.step(rst_n=False))

        for pin in pin_values:
            trace.append(self.step(pin_in=pin))

        return trace
