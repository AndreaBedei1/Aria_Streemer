import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple, Any

LOG = logging.getLogger(__name__)

@dataclass
class Detection:
    label: str
    confidence: float
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2
    model_name: str

class VisionBackend:
    def predict(self, frame_or_crop: Any, gaze_point: Optional[Tuple[float, float]] = None) -> List[Detection]:
        raise NotImplementedError

class YoloWorldBackend(VisionBackend):
    def __init__(self, model_name: str = "yolov8s-worldv2.pt", classes: List[str] = None):
        self.model_name = model_name
        self.model = None
        try:
            from ultralytics import YOLOWorld
            import torch
            device = "cpu"
            if torch.cuda.is_available():
                cap = torch.cuda.get_device_capability()
                if cap[0] >= 7:
                    device = "cuda"
                else:
                    LOG.warning(f"CUDA GPU found but capability {cap} is too old (needs >= 7.0). Falling back to CPU.")
            self.model = YOLOWorld(model_name)
            self.model.to(device)
            if classes:
                self.model.set_classes(classes)
            LOG.info(f"Loaded YOLO-World ({model_name}) on {device}")
        except ImportError:
            LOG.error("ultralytics not installed. YoloWorldBackend unavailable.")
        except Exception as e:
            LOG.error(f"Error loading YOLO-World: {e}")

    def predict(self, frame_or_crop: Any, gaze_point: Optional[Tuple[float, float]] = None) -> List[Detection]:
        if not self.model:
            return []
        try:
            # frame_or_crop is expected to be a numpy array
            results = self.model(frame_or_crop, conf=0.25, verbose=False)
            detections = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    label = result.names[cls_id]
                    conf = box.conf[0].item()
                    xyxy = box.xyxy[0].tolist()
                    detections.append(Detection(label, conf, tuple(xyxy), self.model_name))
            return detections
        except Exception as e:
            LOG.error(f"YOLO predict error: {e}")
            return []
