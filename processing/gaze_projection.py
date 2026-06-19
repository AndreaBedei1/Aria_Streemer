from __future__ import annotations

import math
from typing import Optional, Tuple


def project_gaze_to_rgb(
    yaw_rad: Optional[float],
    pitch_rad: Optional[float],
    image_width: int,
    image_height: int,
    calibration: object | None = None,
) -> Optional[Tuple[float, float]]:
    """Project gaze to RGB.

    If a Project Aria calibration object is wired in later, use it here.
    The fallback maps yaw/pitch to a stable demo overlay in image coordinates.
    """

    if yaw_rad is None or pitch_rad is None:
        return None
    if not (math.isfinite(yaw_rad) and math.isfinite(pitch_rad)):
        return None

    if calibration is not None:
        # Placeholder for official calibration-based projection.
        # Kept explicit so the fallback is not mistaken for calibrated geometry.
        pass

    yaw_span = math.radians(35.0)
    pitch_span = math.radians(25.0)
    x = 0.5 + max(-1.0, min(1.0, yaw_rad / yaw_span)) * 0.42
    y = 0.5 - max(-1.0, min(1.0, pitch_rad / pitch_span)) * 0.42
    return (x * image_width, y * image_height)


def looking_state(yaw_rad: Optional[float], pitch_rad: Optional[float]) -> str:
    if yaw_rad is None or pitch_rad is None:
        return "Waiting for data..."
    yaw_deg = math.degrees(yaw_rad)
    pitch_deg = math.degrees(pitch_rad)
    if abs(yaw_deg) < 8 and abs(pitch_deg) < 8:
        return "Looking center"
    if abs(yaw_deg) >= abs(pitch_deg):
        return "Looking right" if yaw_deg > 0 else "Looking left"
    return "Looking up" if pitch_deg > 0 else "Looking down"
