import math
from typing import List, Optional, Tuple

from vision_backends import Detection


def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def distance_to_box(point: Tuple[float, float], bbox: Tuple[float, float, float, float]) -> float:
    x, y = point
    x1, y1, x2, y2 = bbox
    dx = max(x1 - x, 0.0, x - x2)
    dy = max(y1 - y, 0.0, y - y2)
    return math.hypot(dx, dy)


def select_object_by_gaze(
    detections: List[Detection], 
    gaze_point: Tuple[float, float], 
    image_shape: Tuple[int, int], 
    max_radius_px: float = 200.0
) -> Optional[Detection]:
    
    if not detections:
        return None
        
    best_det = None
    best_score = -1.0
    img_w, img_h = image_shape
    img_area = max(1.0, float(img_w * img_h))
    
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        width = max(1.0, x2 - x1)
        height = max(1.0, y2 - y1)
        area_ratio = min(1.0, (width * height) / img_area)
        is_inside = (x1 <= gaze_point[0] <= x2) and (y1 <= gaze_point[1] <= y2)

        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        center_dist = distance((cx, cy), gaze_point)
        edge_dist = distance_to_box(gaze_point, det.bbox)

        if edge_dist > max_radius_px:
            continue

        if is_inside:
            gaze_score = 1.35
        else:
            gaze_score = max(0.0, 0.9 * (1.0 - edge_dist / max(1.0, max_radius_px)))

        center_score = max(0.15, 1.0 - center_dist / max(1.0, max_radius_px * 1.5))
        size_score = 1.0 / (1.0 + 3.2 * math.sqrt(area_ratio))
        final_score = det.confidence * gaze_score * center_score * size_score

        if final_score > best_score and det.confidence >= 0.45:
            best_score = final_score
            best_det = det
            
    return best_det
