from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class FIFOResult:
    popped_data: int | None
    push_accepted: bool
    pop_accepted: bool
    overflow: bool
    underflow: bool
    level: int


class BoundedFIFO:
    def __init__(self, depth: int = 4, width: int = 8):
        if depth < 1 or width < 1:
            raise ValueError("depth and width must be positive")
        self.depth = depth
        self.width = width
        self.mask = (1 << width) - 1
        self.queue = deque()

    @property
    def level(self):
        return len(self.queue)

    @property
    def full(self):
        return self.level == self.depth

    @property
    def empty(self):
        return self.level == 0

    def reset(self):
        self.queue.clear()

    def tick(self, push_data: int | None = None, pop: bool = False):
        if push_data is not None:
            if not isinstance(push_data, int) or not 0 <= push_data <= self.mask:
                raise ValueError("push_data is outside the FIFO data width")

        popped_data = None
        push_accepted = False
        pop_accepted = False
        overflow = False
        underflow = False

        if pop:
            if self.queue:
                popped_data = self.queue.popleft()
                pop_accepted = True
            else:
                underflow = True

        if push_data is not None:
            if len(self.queue) < self.depth:
                self.queue.append(push_data)
                push_accepted = True
            else:
                overflow = True

        return FIFOResult(
            popped_data=popped_data,
            push_accepted=push_accepted,
            pop_accepted=pop_accepted,
            overflow=overflow,
            underflow=underflow,
            level=self.level,
        )


@dataclass(frozen=True)
class ShiftResult:
    value: int
    shifted_out: int | None


class ShiftRegister:
    def __init__(self, width: int = 8, value: int = 0):
        if width < 1:
            raise ValueError("width must be positive")
        self.width = width
        self.mask = (1 << width) - 1
        self._validate_value(value)
        self.value = value

    def _validate_value(self, value):
        if not isinstance(value, int) or not 0 <= value <= self.mask:
            raise ValueError("value is outside the shift-register width")

    def tick(
        self,
        load: int | None = None,
        shift_left: bool = False,
        shift_right: bool = False,
        serial_in: int = 0,
        clear: bool = False,
    ):
        if shift_left and shift_right:
            raise ValueError("left and right shifts cannot occur together")
        if serial_in not in (0, 1):
            raise ValueError("serial_in must be 0 or 1")
        if load is not None:
            self._validate_value(load)

        shifted_out = None

        if clear:
            self.value = 0
        elif load is not None:
            self.value = load
        elif shift_left:
            shifted_out = (self.value >> (self.width - 1)) & 1
            self.value = ((self.value << 1) | serial_in) & self.mask
        elif shift_right:
            shifted_out = self.value & 1
            self.value = (self.value >> 1) | (serial_in << (self.width - 1))

        return ShiftResult(
            value=self.value,
            shifted_out=shifted_out,
        )
