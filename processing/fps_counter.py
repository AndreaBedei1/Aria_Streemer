from __future__ import annotations

import time
from collections import deque
from typing import Deque


class FpsCounter:
    def __init__(self, window_s: float = 3.0):
        self.window_s = window_s
        self._ticks: Deque[float] = deque()
        self._last_frame_number = None
        self.dropped_frames = 0

    def tick(self, frame_number: int | None = None) -> float:
        now = time.monotonic()
        self._ticks.append(now)
        while self._ticks and now - self._ticks[0] > self.window_s:
            self._ticks.popleft()

        if frame_number is not None and self._last_frame_number is not None:
            missed = frame_number - self._last_frame_number - 1
            if missed > 0:
                self.dropped_frames += missed
        if frame_number is not None:
            self._last_frame_number = frame_number
        return self.value

    @property
    def value(self) -> float:
        if len(self._ticks) < 2:
            return 0.0
        elapsed = self._ticks[-1] - self._ticks[0]
        if elapsed <= 0:
            return 0.0
        return (len(self._ticks) - 1) / elapsed

    def reset(self) -> None:
        self._ticks.clear()
        self._last_frame_number = None
        self.dropped_frames = 0
