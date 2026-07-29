"""MicroPython time API compatibility layer.

The MicroPython runtime provides these functions, but some editor stub bundles
model ``time`` as CPython's module and omit them. Keeping the dynamic lookup in
one place preserves runtime behavior without scattering type suppressions.
"""

import time as _time


ticks_ms = getattr(_time, "ticks_ms")
ticks_us = getattr(_time, "ticks_us")
ticks_diff = getattr(_time, "ticks_diff")
sleep_ms = getattr(_time, "sleep_ms")

