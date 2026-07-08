from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple
from urllib.request import Request, urlopen

import numpy as np

from stream_state import HandSideSample, HandTrackingSample


LOG = logging.getLogger(__name__)

BBox = Tuple[float, float, float, float]


@dataclass
class GesturePrediction:
    label: str
    confidence: float
    model_name: str
    bbox: Optional[BBox] = None


class HaGridGestureBackend:
    def __init__(
        self,
        weights_path: str,
        weights_url: str = "",
        confidence_threshold: float = 0.35,
        image_size: int = 640,
        device: str = "cpu",
        auto_download: bool = True,
    ) -> None:
        self.weights_path = Path(weights_path).expanduser()
        self.weights_url = weights_url
        self.confidence_threshold = confidence_threshold
        self.image_size = image_size
        self.device = device
        self.model: Any = None
        self.status_message = "HaGRID model not configured"
        self._load_model(auto_download=auto_download)

    @property
    def available(self) -> bool:
        return self.model is not None

    def predict(
        self,
        frame_rgb: Optional[np.ndarray],
        gaze_point: Optional[Tuple[float, float]] = None,
    ) -> Optional[GesturePrediction]:
        if not self.available:
            return None
        if frame_rgb is None:
            return None
        started = time.monotonic()
        try:
            results = self.model(
                frame_rgb,
                conf=self.confidence_threshold,
                imgsz=self.image_size,
                device=self.device,
                verbose=False,
            )
        except Exception as exc:
            self.status_message = f"HaGRID inference failed: {exc}"
            LOG.exception("HaGRID inference failed")
            return None

        detections: list[GesturePrediction] = []
        for result in results:
            for box in result.boxes:
                class_id = int(box.cls[0].item())
                raw_label = result.names.get(class_id, str(class_id))
                label = _display_label(raw_label)
                if label.lower() == "no gesture":
                    continue
                confidence = float(box.conf[0].item())
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                detections.append(
                    GesturePrediction(
                        label=label,
                        confidence=confidence,
                        model_name="HaGRIDv2 YOLOv10n",
                        bbox=(x1, y1, x2, y2),
                    )
                )

        prediction = select_gesture_by_gaze(detections, gaze_point)
        if prediction is not None:
            elapsed_ms = max(1e-6, (time.monotonic() - started) * 1000.0)
            prediction.inference_time_ms = elapsed_ms  # type: ignore[attr-defined]
        return prediction

    def _load_model(self, auto_download: bool) -> None:
        if not self.weights_path.exists() and auto_download:
            self._download_weights()
        if not self.weights_path.exists():
            self.status_message = f"Missing HaGRID weights: {self.weights_path}"
            LOG.info(self.status_message)
            return
        try:
            from ultralytics import YOLO

            self.model = YOLO(str(self.weights_path))
            self.model.to(self.device)
            self.status_message = "HaGRIDv2 YOLOv10n ready"
            LOG.info("Loaded HaGRID gesture model from %s", self.weights_path)
        except ImportError:
            self.status_message = "ultralytics is required for HaGRID gesture detection"
            LOG.warning(self.status_message)
        except Exception as exc:
            self.model = None
            self.status_message = f"HaGRID model unavailable: {exc}"
            LOG.exception("Failed to load HaGRID gesture model")

    def _download_weights(self) -> None:
        if not self.weights_url:
            return
        try:
            self.weights_path.parent.mkdir(parents=True, exist_ok=True)
            request = Request(self.weights_url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=120) as response, self.weights_path.open("wb") as file:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    file.write(chunk)
            LOG.info("Downloaded HaGRID gesture weights to %s", self.weights_path)
        except Exception as exc:
            LOG.warning("Could not download HaGRID gesture weights: %s", exc)
            try:
                if self.weights_path.exists() and self.weights_path.stat().st_size == 0:
                    self.weights_path.unlink()
            except Exception:
                pass


class LandmarkGestureFallbackBackend:
    def __init__(self) -> None:
        self.history: deque[tuple[float, tuple[float, float, float]]] = deque(maxlen=10)
        self.status_message = "Landmark fallback"

    def predict(self, sample: Optional[HandTrackingSample]) -> Optional[GesturePrediction]:
        side = _best_visible_hand(sample)
        if side is None:
            self.history.clear()
            return None

        palm = side.palm_device or side.wrist_device
        if palm is not None:
            self.history.append((time.monotonic(), palm))
            movement = self._movement_prediction()
            if movement is not None:
                return movement

        static = self._static_pose_prediction(side)
        if static is not None:
            return static
        return GesturePrediction("Hand visible", 0.50, "Landmark fallback")

    def _movement_prediction(self) -> Optional[GesturePrediction]:
        if len(self.history) < 5:
            return None
        _, first = self.history[0]
        _, last = self.history[-1]
        dx = last[0] - first[0]
        dy = last[1] - first[1]
        dz = last[2] - first[2]
        axis_delta = max(abs(dx), abs(dy), abs(dz))
        if axis_delta < 0.055:
            return None
        if abs(dx) == axis_delta:
            label = "Move hand right" if dx > 0 else "Move hand left"
        elif abs(dy) == axis_delta:
            label = "Move hand up" if dy > 0 else "Move hand down"
        else:
            label = "Push away" if dz > 0 else "Bring hand close"
        return GesturePrediction(label, min(0.85, 0.55 + axis_delta * 3.0), "Landmark fallback")

    def _static_pose_prediction(self, side: HandSideSample) -> Optional[GesturePrediction]:
        pts = side.landmarks_device
        if len(pts) < 21:
            return None
        palm = np.array(side.palm_device or pts[5], dtype=np.float32)
        fingertips = [np.array(pts[i], dtype=np.float32) for i in (4, 8, 12, 16, 20)]
        distances = [float(np.linalg.norm(tip - palm)) for tip in fingertips]
        avg_distance = sum(distances) / len(distances)
        spread = _point_spread(fingertips)
        if avg_distance < 0.095:
            return GesturePrediction("Fist", 0.68, "Landmark fallback")
        if spread > 0.075:
            return GesturePrediction("Palm", 0.64, "Landmark fallback")
        return GesturePrediction("Point", 0.58, "Landmark fallback")


def select_gesture_by_gaze(
    detections: Sequence[GesturePrediction],
    gaze_point: Optional[Tuple[float, float]],
    max_radius_px: float = 220.0,
) -> Optional[GesturePrediction]:
    if not detections:
        return None
    if gaze_point is None:
        return max(detections, key=lambda det: det.confidence)

    best: Optional[GesturePrediction] = None
    best_score = -1.0
    for detection in detections:
        if detection.bbox is None:
            score = detection.confidence * 0.25
        else:
            edge_dist = _distance_to_box(gaze_point, detection.bbox)
            if edge_dist > max_radius_px:
                continue
            center = (
                (detection.bbox[0] + detection.bbox[2]) / 2.0,
                (detection.bbox[1] + detection.bbox[3]) / 2.0,
            )
            center_dist = math.hypot(center[0] - gaze_point[0], center[1] - gaze_point[1])
            proximity = max(0.1, 1.0 - edge_dist / max(1.0, max_radius_px))
            center_bonus = max(0.25, 1.0 - center_dist / max(1.0, max_radius_px * 1.5))
            score = detection.confidence * proximity * center_bonus
        if score > best_score:
            best_score = score
            best = detection
    return best


def _best_visible_hand(sample: Optional[HandTrackingSample]) -> Optional[HandSideSample]:
    if sample is None:
        return None
    candidates = [side for side in (sample.right, sample.left) if side.visible and side.landmarks_device]
    if not candidates:
        return None
    return max(candidates, key=lambda side: side.confidence or 0.0)


def _distance_to_box(point: Tuple[float, float], bbox: BBox) -> float:
    x, y = point
    x1, y1, x2, y2 = bbox
    dx = max(x1 - x, 0.0, x - x2)
    dy = max(y1 - y, 0.0, y - y2)
    return math.hypot(dx, dy)


def _point_spread(points: Sequence[np.ndarray]) -> float:
    if len(points) < 2:
        return 0.0
    spread = 0.0
    for i, point in enumerate(points):
        for other in points[i + 1 :]:
            spread = max(spread, float(np.linalg.norm(point - other)))
    return spread


def _display_label(label: str) -> str:
    special = {
        "ok": "OK",
        "xsign": "X sign",
        "no_gesture": "No gesture",
    }
    if label in special:
        return special[label]
    return label.replace("_", " ").strip().capitalize()
