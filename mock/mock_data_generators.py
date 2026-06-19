from __future__ import annotations

import math
import time
from typing import List, Tuple

import numpy as np

from stream_state import HandSideSample, Point3D


def rgb_frame(width: int, height: int, t: float) -> np.ndarray:
    x = np.linspace(0, 1, width, dtype=np.float32)
    y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    r = 70 + 80 * x + 30 * np.sin(t * 0.7)
    g = 80 + 90 * y + 20 * np.cos(t * 0.5)
    b = 110 + 40 * (1 - x) + 25 * np.sin(t * 0.3 + y * 4)
    frame = np.dstack(
        [
            np.broadcast_to(r, (height, width)),
            np.broadcast_to(g, (height, width)),
            np.broadcast_to(b, (height, width)),
        ]
    )
    cx = int(width * (0.5 + 0.25 * math.sin(t * 0.35)))
    cy = int(height * (0.55 + 0.15 * math.cos(t * 0.42)))
    yy, xx = np.ogrid[:height, :width]
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 < (min(width, height) * 0.08) ** 2
    frame[mask] = [235, 200, 90]
    return np.clip(frame, 0, 255).astype(np.uint8)


def et_frame(size: int, t: float, side: str) -> np.ndarray:
    img = np.full((size, size, 3), 30, dtype=np.uint8)
    cx = int(size * (0.5 + 0.12 * math.sin(t * 1.1 + (0 if side == "left" else 1))))
    cy = int(size * (0.5 + 0.08 * math.cos(t * 0.9)))
    yy, xx = np.ogrid[:size, :size]
    iris = (xx - cx) ** 2 + (yy - cy) ** 2 < (size * 0.18) ** 2
    pupil = (xx - cx) ** 2 + (yy - cy) ** 2 < (size * 0.08) ** 2
    img[iris] = [105, 125, 140]
    img[pupil] = [5, 8, 12]
    return img


def gaze(t: float) -> Tuple[float, float, bool]:
    blink_phase = int(t * 2.0) % 17
    valid = blink_phase not in {0}
    yaw = math.radians(12.0 * math.sin(t * 0.55))
    pitch = math.radians(8.0 * math.sin(t * 0.4 + 0.8))
    return yaw, pitch, valid


def pupil(t: float, lux: float) -> Tuple[float, float]:
    base = 4.6 - min(2.0, math.log10(max(1.0, lux)) * 0.55)
    wave = 0.18 * math.sin(t * 0.3)
    return max(2.0, base + wave), max(2.0, base + wave * 0.9 + 0.05)


def ppg_value(t: float, bpm: float = 74.0) -> float:
    freq = bpm / 60.0
    pulse = math.sin(2 * math.pi * freq * t)
    harmonic = 0.35 * math.sin(2 * math.pi * freq * 2 * t + 0.6)
    resp = 0.15 * math.sin(2 * math.pi * 0.22 * t)
    noise = np.random.normal(0.0, 0.04)
    return 1000.0 + 35.0 * (pulse + harmonic + resp + noise)


def ambient_lux(t: float) -> Tuple[float, str]:
    lux = 260.0 + 180.0 * math.sin(t * 0.05)
    if lux < 120:
        state = "low light"
    elif lux < 450:
        state = "medium light"
    else:
        state = "bright light"
    return lux, state


def hand_side(t: float, side: str) -> HandSideSample:
    visible = int(t / 6) % 5 != 0
    if not visible:
        return HandSideSample(False)
    sx = -0.12 if side == "left" else 0.12
    landmarks: List[Point3D] = []
    palm = np.array([sx, 0.0, 0.45])
    landmarks.append(tuple((palm + [0.00, 0.11, 0.0]).tolist()))
    landmarks.append(tuple((palm + [0.05, 0.16, 0.0]).tolist()))
    landmarks.append(tuple((palm + [0.02, 0.19, 0.0]).tolist()))
    landmarks.append(tuple((palm + [-0.02, 0.17, 0.0]).tolist()))
    landmarks.append(tuple((palm + [-0.06, 0.14, 0.0]).tolist()))
    landmarks.append(tuple((palm + [0.0, -0.08, 0.0]).tolist()))
    for finger in range(5):
        base_x = sx + (finger - 2) * 0.025
        for joint in range(3):
            bend = 0.015 * math.sin(t * 1.3 + finger)
            landmarks.append((base_x + bend, 0.02 + joint * 0.045, 0.45 + joint * 0.005))
    return HandSideSample(
        visible=True,
        confidence=0.82 + 0.1 * math.sin(t),
        landmarks_device=landmarks[:21],
        wrist_device=(sx, -0.08, 0.45),
        palm_device=(sx, 0.0, 0.45),
    )
