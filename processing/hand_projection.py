from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from stream_state import Point3D


def project_hand_to_camera(
    landmarks_device: Iterable[Point3D],
    image_width: int,
    image_height: int,
    calibration: object | None = None,
) -> List[Tuple[float, float]]:
    """Project hand landmarks to a camera plane.

    The current fallback is an orthographic sketch for the hand widget. Replace
    this with official Project Aria calibration projection when available.
    """

    pts = list(landmarks_device)
    if not pts:
        return []

    if calibration is not None:
        pass

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(1e-6, max_x - min_x)
    span_y = max(1e-6, max_y - min_y)
    out: List[Tuple[float, float]] = []
    for x, y, _ in pts:
        nx = (x - min_x) / span_x
        ny = (y - min_y) / span_y
        out.append((nx * image_width, (1.0 - ny) * image_height))
    return out


HAND_CONNECTIONS: List[Tuple[int, int]] = [
    (5, 17),
    (17, 18),
    (18, 19),
    (19, 4),
    (5, 14),
    (14, 15),
    (15, 16),
    (16, 3),
    (5, 11),
    (11, 12),
    (12, 13),
    (13, 2),
    (5, 8),
    (8, 9),
    (9, 10),
    (10, 1),
    (5, 6),
    (6, 7),
    (7, 0),
    (6, 8),
    (8, 11),
    (11, 14),
    (14, 17),
]
