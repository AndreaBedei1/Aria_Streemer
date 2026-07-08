from __future__ import annotations

import math
from typing import Optional, Tuple


def project_gaze_to_rgb(
    yaw_rad: Optional[float],
    pitch_rad: Optional[float],
    image_width: int,
    image_height: int,
    camera_label: str = "",
    calibration: object | None = None,
    eyegaze_data: object | None = None,
) -> Optional[Tuple[float, float]]:
    """Project gaze to RGB.

    If a Project Aria calibration object is wired in later, use it here.
    The fallback maps yaw/pitch to a stable demo overlay in image coordinates.
    """

    if yaw_rad is None or pitch_rad is None:
        return None
    if not (math.isfinite(yaw_rad) and math.isfinite(pitch_rad)):
        return None

    if calibration is not None and eyegaze_data is not None:
        try:
            from projectaria_tools.core.mps.utils import get_gaze_vector_reprojection
            stream_id = "camera-rgb" if "RGB" in camera_label.upper() else "camera-slam-left"
            camera_calib = calibration.get_camera_calib(stream_id)
            if camera_calib is not None:
                depth_m = getattr(eyegaze_data, "depth", 1.0)
                if depth_m is None or not math.isfinite(depth_m):
                    depth_m = 1.0
                pt = get_gaze_vector_reprojection(
                    eyegaze_data,
                    stream_id,
                    calibration,
                    camera_calib,
                    depth_m,
                    make_upright=False
                )
                if pt is not None:
                    # The projection returns pixel coordinates in the original sensor resolution.
                    # We must scale it to the current display resolution.
                    full_width, full_height = camera_calib.get_image_size()
                    return (float(pt[0]) * (image_width / full_width), float(pt[1]) * (image_height / full_height))
        except Exception:
            pass

    if "RGB" in camera_label.upper():
        yaw_span = math.radians(55.0)  # ~110 deg FOV
        pitch_span = math.radians(45.0) # ~90 deg FOV
    else:
        yaw_span = math.radians(75.0)  # ~150 deg FOV for SLAM
        pitch_span = math.radians(60.0)

    # In Aria Gen 2 egocentric view, X is right, Y is down
    # Yaw positive = left (moves towards X=0)
    # Pitch positive = up (moves towards Y=0)
    x = 0.5 - max(-1.0, min(1.0, yaw_rad / yaw_span)) * 0.5
    y = 0.5 - max(-1.0, min(1.0, pitch_rad / pitch_span)) * 0.5
    return (x * image_width, y * image_height)


def looking_state(yaw_rad: Optional[float], pitch_rad: Optional[float]) -> str:
    if yaw_rad is None or pitch_rad is None:
        return "Waiting for data..."
    yaw_deg = math.degrees(yaw_rad)
    pitch_deg = math.degrees(pitch_rad)
    if abs(yaw_deg) < 8 and abs(pitch_deg) < 8:
        return "Looking center"
    if abs(yaw_deg) >= abs(pitch_deg):
        return "Looking left" if yaw_deg > 0 else "Looking right"
    return "Looking up" if pitch_deg > 0 else "Looking down"
