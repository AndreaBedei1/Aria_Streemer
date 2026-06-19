from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, List, Tuple

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover - runtime dependency
    cv2 = None


@dataclass
class RateLimiter:
    rate_hz: float
    _last_emit: float = 0.0

    def allow(self) -> bool:
        now = time.monotonic()
        period = 1.0 / max(0.001, self.rate_hz)
        if now - self._last_emit >= period:
            self._last_emit = now
            return True
        return False


def resize_keep_aspect(frame: np.ndarray, max_width: int, max_height: int) -> np.ndarray:
    if frame is None or frame.size == 0:
        return frame
    height, width = frame.shape[:2]
    scale = min(max_width / max(1, width), max_height / max(1, height), 1.0)
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    if new_width == width and new_height == height:
        return frame
    if cv2 is not None:
        return cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
    y_idx = np.linspace(0, height - 1, new_height).astype(int)
    x_idx = np.linspace(0, width - 1, new_width).astype(int)
    return frame[y_idx][:, x_idx]


def decimate_points(
    points: Iterable[Tuple[float, float]], max_points: int
) -> List[Tuple[float, float]]:
    pts = list(points)
    if len(pts) <= max_points:
        return pts
    step = int(np.ceil(len(pts) / max_points))
    return pts[::step][-max_points:]
