from __future__ import annotations

import math

from processing.gaze_projection import looking_state, project_gaze_to_rgb


def test_gaze_fallback_positive_yaw_projects_left() -> None:
    point = project_gaze_to_rgb(math.radians(15), 0.0, 1000, 500)

    assert point is not None
    assert point[0] < 500


def test_gaze_fallback_negative_yaw_projects_right() -> None:
    point = project_gaze_to_rgb(math.radians(-15), 0.0, 1000, 500)

    assert point is not None
    assert point[0] > 500


def test_looking_state_matches_live_yaw_sign() -> None:
    assert looking_state(math.radians(12), 0.0) == "Looking left"
    assert looking_state(math.radians(-12), 0.0) == "Looking right"
    assert looking_state(0.0, 0.0) == "Looking center"
