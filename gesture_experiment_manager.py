from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Optional

from gesture_recognition_backend import (
    GesturePrediction,
    HaGridGestureBackend,
    LandmarkGestureFallbackBackend,
)
from speech_announcer import SpeechAnnouncer


LOG = logging.getLogger(__name__)


class GestureExperimentManager:
    def __init__(self, config: Any, state: Any):
        self.config = config
        self.state = state
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.is_active = False
        self.history = deque(maxlen=3)
        self.last_stable_gesture: Optional[GesturePrediction] = None
        self.last_inference_fps = 0.0
        self.inference_interval = 1.0
        self.min_speech_confidence = 0.80
        self.speech_cooldown_s = 4.0
        self._last_spoken_at = 0.0
        self._last_spoken_label = ""
        self.speech = SpeechAnnouncer()

        cfg = self._load_config()
        self.inference_interval = float(cfg.get("inference_interval", self.inference_interval))
        self.min_speech_confidence = float(cfg.get("min_speech_confidence", self.min_speech_confidence))
        self.speech_cooldown_s = float(cfg.get("speech_cooldown_s", self.speech_cooldown_s))
        self.fallback_backend = LandmarkGestureFallbackBackend()
        self.hagrid_backend = HaGridGestureBackend(
            weights_path=str(cfg.get("weights_path", "./weights/hagrid/YOLOv10n_gestures.pt")),
            weights_url=str(
                cfg.get(
                    "weights_url",
                    "https://rndml-team-cv.obs.ru-moscow-1.hc.sbercloud.ru/datasets/hagrid_v2/models/YOLOv10n_gestures.pt",
                )
            ),
            confidence_threshold=float(cfg.get("confidence_threshold", 0.35)),
            image_size=int(cfg.get("image_size", 640)),
            device=str(cfg.get("device", "cpu")),
            auto_download=bool(cfg.get("auto_download", True)),
        )

    def start_experiment(self, output_dir: str) -> None:
        del output_dir
        if self.is_active:
            return

        toggles = self.state.get_toggles()
        toggles.rgb = True
        toggles.hand_tracking = True
        self.state.set_toggles(toggles)

        self.is_active = True
        self._stop_event.clear()
        self.history.clear()
        self.last_stable_gesture = None
        self.state.gesture_experiment_result = {
            "label": "Initializing...",
            "conf": 0.0,
            "fps": 0.0,
            "bbox": None,
            "source": self._source_label(),
            "active": True,
        }
        self._thread = threading.Thread(target=self._run_loop, name="gesture-experiment-worker", daemon=True)
        self._thread.start()

    def stop_experiment(self) -> None:
        self.speech.cancel()
        if not self.is_active:
            return
        self.is_active = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self.state.gesture_experiment_result = {
            "label": "Stopped",
            "conf": 0.0,
            "fps": 0.0,
            "bbox": None,
            "source": self._source_label(),
            "active": False,
        }

    def close(self) -> None:
        self.stop_experiment()
        self.speech.close()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            started = time.monotonic()
            prediction = self._predict_once()
            if self._stop_event.is_set():
                break
            stable = self._temporal_filter(prediction)
            if stable is not None:
                self.state.gesture_experiment_result = {
                    "label": stable.label,
                    "conf": stable.confidence,
                    "fps": self.last_inference_fps,
                    "bbox": stable.bbox,
                    "source": stable.model_name,
                    "active": True,
                }
                if self._should_speak(stable):
                    self.speech.speak_label(stable.label)
            else:
                self.state.gesture_experiment_result = {
                    "label": "Waiting for hand data",
                    "conf": 0.0,
                    "fps": self.last_inference_fps,
                    "bbox": None,
                    "source": self._source_label(),
                    "active": True,
                }
            elapsed = time.monotonic() - started
            time.sleep(max(0.1, self.inference_interval - elapsed))

    def _predict_once(self) -> Optional[GesturePrediction]:
        frame = self.state.rgb_frame.get()
        started = time.monotonic()
        if self.hagrid_backend.available and frame is not None and frame.valid and frame.image_rgb is not None:
            eye = self.state.eye_tracking.get()
            gaze_point = eye.gaze_point_rgb if eye else None
            prediction = self.hagrid_backend.predict(frame.image_rgb, gaze_point)
            elapsed_ms = getattr(prediction, "inference_time_ms", 0.0) if prediction else 0.0
            self.last_inference_fps = 1000.0 / elapsed_ms if elapsed_ms else 0.0
            if prediction is not None:
                return prediction

        fallback = self.fallback_backend.predict(self.state.hand_tracking.get())
        elapsed_ms = (time.monotonic() - started) * 1000.0
        self.last_inference_fps = 1000.0 / elapsed_ms if elapsed_ms > 0 else 0.0
        return fallback

    def _temporal_filter(self, prediction: Optional[GesturePrediction]) -> Optional[GesturePrediction]:
        self.history.append(prediction.label if prediction else None)
        if len(self.history) < 3:
            return prediction
        counts: dict[str, int] = {}
        for label in self.history:
            if label:
                counts[label] = counts.get(label, 0) + 1
        if not counts:
            self.last_stable_gesture = None
            return None
        label, count = max(counts.items(), key=lambda item: item[1])
        if count >= 2 and prediction and prediction.label == label:
            self.last_stable_gesture = prediction
        return self.last_stable_gesture

    def _should_speak(self, prediction: GesturePrediction) -> bool:
        if prediction.confidence < self.min_speech_confidence:
            return False
        now = time.monotonic()
        if now - self._last_spoken_at < self.speech_cooldown_s:
            return False
        self._last_spoken_at = now
        self._last_spoken_label = prediction.label
        return True

    def _source_label(self) -> str:
        if self.hagrid_backend.available:
            return "HaGRIDv2 YOLOv10n"
        return self.hagrid_backend.status_message or self.fallback_backend.status_message

    @staticmethod
    def _load_config() -> dict[str, Any]:
        try:
            import yaml

            with open("config/experiment_config.yaml", "r", encoding="utf-8") as file:
                return (yaml.safe_load(file) or {}).get("gesture_experiment", {}) or {}
        except Exception as exc:
            LOG.error("Failed to load gesture experiment config: %s", exc)
            return {}
