from __future__ import annotations

import time

from gesture_recognition_backend import (
    GesturePrediction,
    HaGridGestureBackend,
    LandmarkGestureFallbackBackend,
    select_gesture_by_gaze,
)
from mock.mock_data_generators import hand_side
from stream_state import HandSideSample, HandTrackingSample


def test_hagrid_missing_weights_is_non_fatal(tmp_path) -> None:
    backend = HaGridGestureBackend(
        weights_path=str(tmp_path / "missing_weights.pth"),
        auto_download=False,
    )

    assert not backend.available
    assert backend.predict(None) is None
    assert "Missing" in backend.status_message


def test_select_gesture_by_gaze_prefers_box_near_gaze() -> None:
    detections = [
        GesturePrediction("Monitor hand", 0.95, "test", (50.0, 50.0, 300.0, 300.0)),
        GesturePrediction("Palm", 0.70, "test", (410.0, 205.0, 500.0, 310.0)),
    ]

    selected = select_gesture_by_gaze(detections, gaze_point=(450.0, 250.0))

    assert selected is detections[1]


def test_landmark_fallback_detects_visible_hand_pose() -> None:
    backend = LandmarkGestureFallbackBackend()
    sample = HandTrackingSample(
        timestamp_s=time.monotonic(),
        left=HandSideSample(False),
        right=hand_side(7.0, "right"),
    )

    prediction = backend.predict(sample)

    assert prediction is not None
    assert prediction.label in {"Palm", "Fist", "Point", "Hand visible"}
    assert prediction.confidence > 0.0


def test_landmark_fallback_returns_none_without_visible_hands() -> None:
    backend = LandmarkGestureFallbackBackend()
    sample = HandTrackingSample(timestamp_s=time.monotonic())

    assert backend.predict(sample) is None
