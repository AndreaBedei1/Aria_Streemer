import logging
import threading
import time
from collections import deque
from typing import Any, Optional, Tuple, List
import numpy as np
try:
    import cv2
except ImportError:
    cv2 = None

from vision_backends import YoloWorldBackend, Detection
from gaze_object_selector import select_object_by_gaze
from experiment_logger import ExperimentLogger

LOG = logging.getLogger(__name__)

class ExperimentManager:
    def __init__(self, config: Any, state: Any):
        self.config = config
        self.state = state
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.is_active = False
        
        self.backend = None
        self.logger = None
        
        # Temporal filtering
        self.history = deque(maxlen=3)
        self.last_stable_object: Optional[Detection] = None
        self.last_inference_fps = 0.0
        
        self.inference_interval = 2.0
        self.crop_size = 640
        self.model_name = "yolov8s-worldv2.pt"
        self.classes = []
        self.max_radius_px = 200.0
        
        try:
            import yaml
            with open("config/experiment_config.yaml", "r") as f:
                exp_cfg = yaml.safe_load(f).get("experiment", {})
                self.inference_interval = exp_cfg.get("inference_interval", 2.0)
                self.model_name = exp_cfg.get("model_name", "yolov8s-worldv2.pt")
                self.crop_size = exp_cfg.get("crop_size", 640)
                self.classes = exp_cfg.get("classes", [])
                self.max_radius_px = exp_cfg.get("max_radius_px", 200.0)
        except Exception as e:
            LOG.error(f"Failed to load experiment config: {e}")
        
    def start_experiment(self, output_dir: str):
        if self.is_active:
            return
            
        LOG.info("Starting experiment...")
        
        # Disable other streams
        toggles = self.state.get_toggles()
        toggles.heart_rate = False
        toggles.ppg_quality = False
        toggles.pulse_variability = False
        toggles.hand_tracking = False
        toggles.als = False
        toggles.temperature = False
        toggles.performance = False
        toggles.eye_tracking = True
        toggles.rgb = True
        toggles.gaze_overlay = True
        self.state.set_toggles(toggles)
        
        # Initialize Backend
        if not self.backend:
            LOG.info("Loading Vision Backend...")
            self.backend = YoloWorldBackend(model_name="yolov8s-worldv2.pt", classes=self.classes)
            
        # Initialize Logger
        self.logger = ExperimentLogger(output_dir)
        
        self.is_active = True
        self._stop_event.clear()
        self.history.clear()
        self.last_stable_object = None
        self.state.experiment_result = {"label": "Initializing...", "conf": 0.0, "fps": 0.0}
        
        self._thread = threading.Thread(target=self._run_loop, name="experiment-worker", daemon=True)
        self._thread.start()
        
    def stop_experiment(self):
        if not self.is_active:
            return
            
        LOG.info("Stopping experiment...")
        self.is_active = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=2.0)
            
        if self.logger:
            self.logger.close()
            self.logger = None
            
        self.state.experiment_result = {"label": "Stopped", "conf": 0.0, "fps": 0.0}

    def _temporal_filter(self, new_det: Optional[Detection]) -> Optional[Detection]:
        if not new_det:
            self.history.append(None)
        else:
            self.history.append(new_det.label)
            
        if len(self.history) < 3:
            return new_det
            
        # Count occurrences
        counts = {}
        for lbl in self.history:
            if lbl:
                counts[lbl] = counts.get(lbl, 0) + 1
                
        # Find most frequent
        best_lbl = None
        best_count = 0
        for lbl, count in counts.items():
            if count > best_count:
                best_count = count
                best_lbl = lbl
                
        if best_count >= 2:
            # We found a stable label
            if new_det and new_det.label == best_lbl:
                self.last_stable_object = new_det
            return self.last_stable_object
            
        return None

    def _run_loop(self):
        while not self._stop_event.is_set():
            t_start = time.time()
            
            frame_data = self.state.rgb_frame.get()
            eye_data = self.state.eye_tracking.get()
            
            if frame_data is not None and frame_data.image_rgb is not None:
                img = frame_data.image_rgb
                gaze_point = eye_data.gaze_point_rgb if eye_data else None
                
                # Crop logic
                crop_size = self.crop_size
                h, w = img.shape[:2]
                
                # Use gaze if available, else center
                if gaze_point and 0 <= gaze_point[0] <= w and 0 <= gaze_point[1] <= h:
                    cx, cy = int(gaze_point[0]), int(gaze_point[1])
                else:
                    cx, cy = w // 2, h // 2
                    gaze_point = (cx, cy)
                
                # If frame is small, just use the whole frame, otherwise crop
                if h >= 1080 and w >= 1080:
                    half = crop_size // 2
                    x1 = max(0, cx - half)
                    y1 = max(0, cy - half)
                    x2 = min(w, cx + half)
                    y2 = min(h, cy + half)
                    
                    # Adjust if hitting bounds
                    if x1 == 0: x2 = min(w, crop_size)
                    if y1 == 0: y2 = min(h, crop_size)
                    if x2 == w: x1 = max(0, w - crop_size)
                    if y2 == h: y1 = max(0, h - crop_size)
                    
                    crop = img[y1:y2, x1:x2].copy()
                    offset_x, offset_y = x1, y1
                else:
                    crop = img
                    offset_x, offset_y = 0, 0
                
                # Inference
                inf_start = time.time()
                detections = self.backend.predict(crop) if self.backend else []
                inf_time_ms = (time.time() - inf_start) * 1000.0
                self.last_inference_fps = 1000.0 / inf_time_ms if inf_time_ms > 0 else 0.0
                
                # Adjust detections to full image coordinates
                for det in detections:
                    bx1, by1, bx2, by2 = det.bbox
                    det.bbox = (bx1 + offset_x, by1 + offset_y, bx2 + offset_x, by2 + offset_y)
                
                # Select best object
                best_det = select_object_by_gaze(detections, gaze_point, (w, h), self.max_radius_px)
                
                # Filter
                stable_det = self._temporal_filter(best_det)
                
                # Update state
                if stable_det:
                    self.state.experiment_result = {
                        "label": stable_det.label, 
                        "conf": stable_det.confidence,
                        "fps": self.last_inference_fps
                    }
                else:
                    self.state.experiment_result = {
                        "label": "unknown", 
                        "conf": 0.0,
                        "fps": self.last_inference_fps
                    }
                    
                # Log
                if self.logger:
                    self.logger.log_event(gaze_point, stable_det, inf_time_ms)
                    
            # Wait for next interval
            elapsed = time.time() - t_start
            sleep_time = max(0.1, self.inference_interval - elapsed)
            time.sleep(sleep_time)
