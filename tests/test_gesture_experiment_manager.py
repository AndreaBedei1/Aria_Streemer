from __future__ import annotations

from gesture_experiment_manager import GestureExperimentManager
from gesture_recognition_backend import GesturePrediction


def test_gesture_speech_requires_high_confidence_and_cooldown() -> None:
    manager = object.__new__(GestureExperimentManager)
    manager.min_speech_confidence = 0.80
    manager.speech_cooldown_s = 60.0
    manager._last_spoken_at = 0.0
    manager._last_spoken_label = ""

    assert not manager._should_speak(GesturePrediction("Palm", 0.79, "test"))
    assert manager._should_speak(GesturePrediction("Palm", 0.80, "test"))
    assert not manager._should_speak(GesturePrediction("Fist", 0.95, "test"))
