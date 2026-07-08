import math
from typing import List, Optional, Tuple
from vision_backends import Detection

def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

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
    
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        is_inside = (x1 <= gaze_point[0] <= x2) and (y1 <= gaze_point[1] <= y2)
        
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        dist = distance((cx, cy), gaze_point)
        
        prox_score = 0.0
        if is_inside:
            # Area penalty to favor smaller objects if inside
            area = (x2 - x1) * (y2 - y1)
            img_area = image_shape[0] * image_shape[1]
            area_ratio = min(1.0, area / img_area)
            prox_score = 1.0 - (area_ratio * 0.3)
        elif dist < max_radius_px:
            prox_score = max(0.1, 0.8 - 0.7 * (dist / max_radius_px))
            
        final_score = det.confidence * prox_score
        
        if final_score > best_score and det.confidence >= 0.45:
            best_score = final_score
            best_det = det
            
    return best_det
