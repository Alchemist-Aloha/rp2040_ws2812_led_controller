"""Interrupt-driven NEC infrared receiver for MicroPython.

The public ``irGetCMD.ir_read()`` API is retained for compatibility. It returns
a hexadecimal string such as ``"0xffa25d"``, or ``"0x000000"`` when no valid
frame is ready.
"""

import machine
import micropython
import mp_time as utime


micropython.alloc_emergency_exception_buf(100)


class irGetCMD:
    # NEC timings include generous margins for inexpensive receivers/remotes.
    _FRAME_GAP_US = 12000
    _LEADER_MARK_MIN = 7000
    _LEADER_MARK_MAX = 11000
    _LEADER_SPACE_MIN = 3500
    _LEADER_SPACE_MAX = 5500
    _REPEAT_SPACE_MIN = 1700
    _REPEAT_SPACE_MAX = 3000
    _BIT_MARK_MIN = 300
    _BIT_MARK_MAX = 900
    _ZERO_SPACE_MIN = 300
    _ZERO_SPACE_MAX = 900
    _ONE_SPACE_MIN = 1200
    _ONE_SPACE_MAX = 2200
    _MAX_EDGES = 70
    _REPEAT_MAX_AGE_US = 250000
    _NO_COMMAND = "0x000000"

    def __init__(self, gpioNum, allow_extended=False, return_repeats=False):
        self.irRecv = machine.Pin(gpioNum, machine.Pin.IN, machine.Pin.PULL_UP)
        self.allow_extended = allow_extended
        self.return_repeats = return_repeats

        # This buffer is allocated once. The IRQ handler only writes existing
        # entries and never grows a list or creates a dictionary.
        self._durations = [0] * self._MAX_EDGES
        self._count = 0
        self._last_edge = None
        self._overflow = False
        self._last_command = None
        self._last_command_time = 0

        self.irRecv.irq(
            trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING,
            handler=self.__logHandler,
        )

    def __logHandler(self, source):
        now = utime.ticks_us()
        previous = self._last_edge
        self._last_edge = now

        if previous is None:
            return

        duration = utime.ticks_diff(now, previous)
        if duration > self._FRAME_GAP_US:
            # The current edge starts a new transmission after an idle gap.
            self._count = 0
            self._overflow = False
            return

        if self._overflow:
            return

        index = self._count
        if index >= self._MAX_EDGES:
            self._overflow = True
            return

        self._durations[index] = duration
        self._count = index + 1

    @staticmethod
    def _in_range(value, minimum, maximum):
        return minimum <= value <= maximum

    def _take_frame(self):
        """Atomically detach a completed capture from the IRQ handler."""
        last_edge = self._last_edge
        if last_edge is None:
            return None
        if utime.ticks_diff(utime.ticks_us(), last_edge) < self._FRAME_GAP_US:
            return None

        irq_state = machine.disable_irq()
        try:
            if self._overflow:
                frame = None
            else:
                frame = self._durations[: self._count]
            self._count = 0
            self._last_edge = None
            self._overflow = False
        finally:
            machine.enable_irq(irq_state)
        return frame

    def _is_repeat_frame(self, frame):
        return (
            len(frame) >= 2
            and self._in_range(
                frame[0], self._LEADER_MARK_MIN, self._LEADER_MARK_MAX
            )
            and self._in_range(
                frame[1], self._REPEAT_SPACE_MIN, self._REPEAT_SPACE_MAX
            )
        )

    def _decode_nec(self, frame):
        # Leader mark + leader space + 32 mark/space bit pairs.
        if len(frame) < 66:
            return None
        if not self._in_range(
            frame[0], self._LEADER_MARK_MIN, self._LEADER_MARK_MAX
        ):
            return None
        if not self._in_range(
            frame[1], self._LEADER_SPACE_MIN, self._LEADER_SPACE_MAX
        ):
            return None

        data = [0, 0, 0, 0]
        for bit_index in range(32):
            mark = frame[2 + bit_index * 2]
            space = frame[3 + bit_index * 2]
            if not self._in_range(mark, self._BIT_MARK_MIN, self._BIT_MARK_MAX):
                return None

            if self._in_range(
                space, self._ZERO_SPACE_MIN, self._ZERO_SPACE_MAX
            ):
                bit = 0
            elif self._in_range(
                space, self._ONE_SPACE_MIN, self._ONE_SPACE_MAX
            ):
                bit = 1
            else:
                return None

            # NEC transmits each byte least-significant bit first.
            data[bit_index // 8] |= bit << (bit_index % 8)

        address, address_inverse, command, command_inverse = data
        if (command ^ command_inverse) != 0xFF:
            return None
        if not self.allow_extended and (address ^ address_inverse) != 0xFF:
            return None

        return (
            (address << 24)
            | (address_inverse << 16)
            | (command << 8)
            | command_inverse
        )

    def ir_read(self):
        frame = self._take_frame()
        if not frame:
            return self._NO_COMMAND

        now = utime.ticks_us()
        if self._is_repeat_frame(frame):
            if (
                self.return_repeats
                and self._last_command is not None
                and utime.ticks_diff(now, self._last_command_time)
                <= self._REPEAT_MAX_AGE_US
            ):
                self._last_command_time = now
                return hex(self._last_command)
            return self._NO_COMMAND

        command = self._decode_nec(frame)
        if command is None:
            return self._NO_COMMAND

        self._last_command = command
        self._last_command_time = now
        return hex(command)
