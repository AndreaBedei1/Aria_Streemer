from __future__ import annotations

from gaze_object_selector import select_object_by_gaze
from vision_backends import Detection


def test_gaze_selector_prefers_small_object_under_gaze_over_large_background() -> None:
    detections = [
        Detection("monitor", 0.93, (50, 40, 900, 500), "test"),
        Detection("book", 0.68, (430, 230, 560, 360), "test"),
    ]

    selected = select_object_by_gaze(detections, (492, 292), (960, 540), max_radius_px=170)

    assert selected is not None
    assert selected.label == "book"


def test_gaze_selector_rejects_objects_far_from_gaze() -> None:
    detections = [
        Detection("monitor", 0.97, (650, 60, 940, 320), "test"),
    ]

    selected = select_object_by_gaze(detections, (180, 420), (960, 540), max_radius_px=120)

    assert selected is None
