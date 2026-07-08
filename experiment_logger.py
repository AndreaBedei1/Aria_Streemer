import csv
import logging
import time
from pathlib import Path
from typing import Optional

LOG = logging.getLogger(__name__)

class ExperimentLogger:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.output_dir / f"experiment_log_{int(time.time())}.csv"
        self.file = None
        self.writer = None
        
        try:
            self.file = open(self.log_file, "w", newline="")
            self.writer = csv.writer(self.file)
            self.writer.writerow([
                "timestamp", 
                "gaze_x", 
                "gaze_y", 
                "detection_label", 
                "confidence", 
                "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
                "inference_time_ms"
            ])
            LOG.info(f"Experiment logger initialized: {self.log_file}")
        except Exception as e:
            LOG.error(f"Failed to initialize experiment logger: {e}")

    def log_event(
        self, 
        gaze_point: Optional[tuple[float, float]], 
        detection: Optional[object], 
        inference_time_ms: float
    ):
        if not self.writer:
            return
            
        gx = f"{gaze_point[0]:.2f}" if gaze_point else ""
        gy = f"{gaze_point[1]:.2f}" if gaze_point else ""
        
        if detection:
            label = detection.label
            conf = f"{detection.confidence:.3f}"
            bx1, by1, bx2, by2 = [f"{v:.2f}" for v in detection.bbox]
        else:
            label = ""
            conf = ""
            bx1 = by1 = bx2 = by2 = ""
            
        try:
            self.writer.writerow([
                f"{time.time():.3f}",
                gx, gy,
                label, conf,
                bx1, by1, bx2, by2,
                f"{inference_time_ms:.1f}"
            ])
            self.file.flush()
        except Exception as e:
            LOG.error(f"Failed to write log event: {e}")
            
    def close(self):
        if self.file:
            try:
                self.file.close()
            except Exception:
                pass
            self.file = None
            self.writer = None
