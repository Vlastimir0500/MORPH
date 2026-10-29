from dataclasses import dataclass

PROGRAM_DEPTH = 64
WORD_MASK = 0xFFFF

STATE_CODES = {
    "FETCH": 0,
    "EXEC": 1,
    "WAIT": 2,
    "EDGE_WAIT": 3,
    "HALT": 4,
    "CAPTURED_WAIT": 5,
}


@dataclass(frozen=True)
class Snapshot:
    cycle: int
    state: str
    pc: int
    instruction: int
    pin_out: int
    pin_oe: int
    sample_reg: int
    shift_reg: int
    wait_count: int
    timed_out: bool
    fault: bool
    executed: str


class MorphISAModelV2:
    def __init__(self):
        self.memory = [0] * PROGRAM_DEPTH
        self.cycle = 0
        self._reset_registers(0)

    def _reset_registers(self, pin_in):
        self.pc = 0
        self.ir = 0
        self.wait_count = 0
        self.loop_remaining = 0
        self.loop_pc = 0
        self.loop_target = 0
        self.loop_active = False
        self.pin_prev = pin_in
        self.edge_last_cycle = 0
        self.edge_interval = 0
        self.edge_seen = False
        self.edge_capture_valid = False
        self.captured_wait_count = 0
        self.sample_reg = 0
        self.sample_history = 0
        self.shift_reg = 0
        self.pin_out = 0
        self.pin_oe = 0
        self.timed_out = False
        self.fault = False
        self.state = "FETCH"

    def load_program(self, words):
        if len(words) > PROGRAM_DEPTH:
            raise ValueError("program exceeds 64 instruction words")
        checked = []
        for word in words:
            if not isinstance(word, int) or not 0 <= word <= WORD_MASK:
                raise ValueError("program words must be unsigned 16-bit integers")
            checked.append(word)
        self.memory = checked + [0] * (PROGRAM_DEPTH - len(checked))

    def step(self, pin_in=0, rst_n=True, program_mode=False):
        if not isinstance(pin_in, int) or not 0 <= pin_in <= 255:
            raise ValueError("pin_in must be an unsigned 8-bit value")

        self.cycle += 1
        executed = "-"
        previous_pin = self.pin_prev

        if not rst_n or program_mode:
            self._reset_registers(pin_in)
            executed = "RESET" if not rst_n else "PROGRAM_MODE"
        else:
            self.pin_prev = pin_in

            if self.state == "FETCH":
                self.ir = self.memory[self.pc]
                self.state = "EXEC"

            elif self.state == "EXEC":
                opcode = (self.ir >> 12) & 0xF
                selector = (self.ir >> 8) & 0xF
                low = self.ir & 0xFF
                pin = selector & 7

                if opcode == 0x0:
                    self.state = "HALT"
                    executed = "HALT"

                elif opcode == 0x1:
                    if selector <= 7:
                        bit = 1 << pin
                        if self.ir & 1:
                            self.pin_out |= bit
                        else:
                            self.pin_out &= ~bit
                        self.pin_oe |= bit
                        self.pc = (self.pc + 1) & 0x3F
                        self.state = "FETCH"
                        executed = "DRIVE"
                    else:
                        self.fault = True
                        self.pin_oe = 0
                        self.state = "HALT"
                        executed = "INVALID_PIN"

                elif opcode == 0x2:
                    if selector <= 7:
                        self.sample_reg = (pin_in >> pin) & 1
                        self.sample_history = ((self.sample_history << 1) | self.sample_reg) & 0x7
                        self.pc = (self.pc + 1) & 0x3F
                        self.state = "FETCH"
                        executed = "SAMPLE"
                    else:
                        self.fault = True
                        self.pin_oe = 0
                        self.state = "HALT"
                        executed = "INVALID_PIN"

                elif opcode == 0x3:
                    if low == 0:
                        self.pc = (self.pc + 1) & 0x3F
                        self.state = "FETCH"
                    else:
                        self.wait_count = low
                        self.state = "WAIT"
                    executed = "WAIT"

                elif opcode == 0x4:
                    if selector <= 7:
                        self.wait_count = (self.ir >> 1) & 0x7F
                        self.state = "EDGE_WAIT"
                        executed = "EDGE"
                    else:
                        self.fault = True
                        self.pin_oe = 0
                        self.state = "HALT"
                        executed = "INVALID_PIN"

                elif opcode == 0x5:
                    self.shift_reg = ((self.shift_reg << 1) | self.sample_reg) & 0xFF
                    self.pc = (self.pc + 1) & 0x3F
                    self.state = "FETCH"
                    executed = "SHIFT"

                elif opcode == 0x6:
                    target = self.ir & 0x3F
                    if self.loop_active and not (self.loop_target <= target <= self.loop_pc):
                        self.loop_active = False
                        self.loop_remaining = 0
                    self.pc = target
                    self.state = "FETCH"
                    executed = "BRANCH"

                elif opcode == 0x7:
                    if selector <= 7:
                        bit = 1 << pin
                        self.pin_out &= ~bit
                        self.pin_oe &= ~bit
                        self.pc = (self.pc + 1) & 0x3F
                        self.state = "FETCH"
                        executed = "RELEASE"
                    else:
                        self.fault = True
                        self.pin_oe = 0
                        self.state = "HALT"
                        executed = "INVALID_PIN"

                elif opcode == 0x8:
                    if self.sample_reg == ((self.ir >> 7) & 1):
                        target = self.ir & 0x3F
                        if self.loop_active and not (self.loop_target <= target <= self.loop_pc):
                            self.loop_active = False
                            self.loop_remaining = 0
                        self.pc = target
                    else:
                        self.pc = (self.pc + 1) & 0x3F
                    self.state = "FETCH"
                    executed = "BRANCH_SAMPLE"

                elif opcode == 0x9:
                    loop_count = (self.ir >> 6) & 0x3F
                    target = self.ir & 0x3F
                    if loop_count == 0 or target >= self.pc:
                        self.fault = True
                        self.pin_oe = 0
                        self.loop_active = False
                        self.loop_remaining = 0
                        self.state = "HALT"
                        executed = "INVALID_LOOP"
                    elif not self.loop_active:
                        if loop_count == 1:
                            self.loop_remaining = 0
                            self.pc = (self.pc + 1) & 0x3F
                            self.state = "FETCH"
                        else:
                            self.loop_active = True
                            self.loop_pc = self.pc
                            self.loop_target = target
                            self.loop_remaining = loop_count - 1
                            self.pc = target
                            self.state = "FETCH"
                        executed = "LOOP"
                    elif self.loop_pc == self.pc:
                        if self.loop_remaining > 1:
                            self.loop_remaining -= 1
                            self.pc = self.loop_target
                            self.state = "FETCH"
                        else:
                            self.loop_active = False
                            self.loop_remaining = 0
                            self.pc = (self.pc + 1) & 0x3F
                            self.state = "FETCH"
                        executed = "LOOP"
                    else:
                        self.fault = True
                        self.pin_oe = 0
                        self.loop_active = False
                        self.loop_remaining = 0
                        self.state = "HALT"
                        executed = "NESTED_LOOP_FAULT"

                elif opcode == 0xA:
                    bits = self.sample_history
                    ones = ((bits >> 2) & 1) + ((bits >> 1) & 1) + (bits & 1)
                    self.sample_reg = 1 if ones >= 2 else 0
                    self.pc = (self.pc + 1) & 0x3F
                    self.state = "FETCH"
                    executed = "VOTE3"

                elif opcode == 0xB:
                    if selector <= 7:
                        self.wait_count = 0
                        self.state = "EDGE_WAIT"
                        executed = "EDGE_CAPTURE"
                    else:
                        self.fault = True
                        self.pin_oe = 0
                        self.state = "HALT"
                        executed = "INVALID_PIN"

                elif opcode == 0xC:
                    if (self.ir & 0x0FFF) == 0 and self.edge_capture_valid and self.edge_interval >= 2:
                        self.captured_wait_count = self.edge_interval >> 1
                        self.state = "CAPTURED_WAIT"
                        executed = "WAIT_HALF_CAPTURED"
                    else:
                        self.fault = True
                        self.pin_oe = 0
                        self.state = "HALT"
                        executed = "INVALID_CAPTURED_WAIT"

                else:
                    self.fault = True
                    self.pin_oe = 0
                    self.state = "HALT"
                    executed = "INVALID_OPCODE" 

            elif self.state == "WAIT":
                if self.wait_count <= 1:
                    self.wait_count = 0
                    self.pc = (self.pc + 1) & 0x3F
                    self.state = "FETCH"
                else:
                    self.wait_count -= 1
                executed = "WAIT_TICK"

            elif self.state == "EDGE_WAIT":
                pin = (self.ir >> 8) & 7
                current = (pin_in >> pin) & 1
                previous = (previous_pin >> pin) & 1
                rising = current == 1 and previous == 0
                falling = current == 0 and previous == 1
                wanted = self.ir & 1

                capture_instruction = ((self.ir >> 12) & 0xF) == 0xB
                capture_any_edge = capture_instruction and bool(self.ir & 0x2)
                edge_match = (rising or falling) if capture_any_edge else ((wanted and rising) or (not wanted and falling))

                if edge_match:
                    if capture_instruction:
                        if self.edge_seen:
                            self.edge_interval = (self.cycle - self.edge_last_cycle) & 0xFFFF
                            self.edge_capture_valid = True
                            self.edge_last_cycle = self.cycle
                            self.wait_count = 0
                            self.pc = (self.pc + 1) & 0x3F
                            self.state = "FETCH"
                        else:
                            self.edge_last_cycle = self.cycle
                            self.edge_seen = True
                    else:
                        self.wait_count = 0
                        self.pc = (self.pc + 1) & 0x3F
                        self.state = "FETCH"
                elif self.wait_count != 0:
                    if self.wait_count <= 1:
                        self.wait_count = 0
                        self.timed_out = True
                        self.fault = True
                        self.pin_oe = 0
                        self.state = "HALT"
                    else:
                        self.wait_count -= 1
                executed = "EDGE_WAIT"

            elif self.state == "CAPTURED_WAIT":
                if self.captured_wait_count <= 1:
                    self.captured_wait_count = 0
                    self.pc = (self.pc + 1) & 0x3F
                    self.state = "FETCH"
                else:
                    self.captured_wait_count -= 1
                executed = "WAIT_HALF_CAPTURED_TICK"

            elif self.state == "HALT":
                executed = "HALTED"

            else:
                self.fault = True
                self.pin_oe = 0
                self.state = "HALT"
                executed = "INVALID_STATE"

        return Snapshot(
            cycle=self.cycle,
            state=self.state,
            pc=self.pc,
            instruction=self.ir,
            pin_out=self.pin_out,
            pin_oe=self.pin_oe,
            sample_reg=self.sample_reg,
            shift_reg=self.shift_reg,
            wait_count=self.wait_count,
            timed_out=self.timed_out,
            fault=self.fault,
            executed=executed,
        )
