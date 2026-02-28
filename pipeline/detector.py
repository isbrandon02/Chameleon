"""YOLOv8 object detection for bottle/can-like objects."""

from ultralytics import YOLO
import cv2
import numpy as np

# COCO class IDs for bottle-like objects
BOTTLE_CLASS_ID = 39      # bottle
WINE_GLASS_ID = 41        # wine glass
CUP_ID = 41               # cup (COCO uses wine glass for cups)
OBJECT_CLASSES = [39, 41]  # bottle, wine glass


def load_model():
    """Load YOLOv8 nano model (lightweight, hackathon-friendly)."""
    return YOLO("yolov8n.pt")


def detect_objects(frame, model, conf_threshold=0.5):
    """
    Detect bottle/can-like objects in a frame.
    
    Returns list of dicts: [{"bbox": (x1,y1,x2,y2), "conf": float, "class_id": int}, ...]
    """
    results = model(frame, verbose=False)[0]
    detections = []
    
    for box in results.boxes:
        class_id = int(box.cls[0])
        conf = float(box.conf[0])
        if class_id in OBJECT_CLASSES and conf >= conf_threshold:
            xyxy = box.xyxy[0].cpu().numpy()
            detections.append({
                "bbox": tuple(map(int, xyxy)),
                "conf": conf,
                "class_id": class_id,
            })
    
    return detections


def get_most_prominent_detection(detections, frame_shape):
    """
    Pick the most prominent object (largest area, centered preference).
    """
    if not detections:
        return None
    
    h, w = frame_shape[:2]
    center_x, center_y = w / 2, h / 2
    
    def score(d):
        x1, y1, x2, y2 = d["bbox"]
        area = (x2 - x1) * (y2 - y1)
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        dist = ((cx - center_x) ** 2 + (cy - center_y) ** 2) ** 0.5
        # Prefer larger, more centered
        return area - dist * 0.1
    
    return max(detections, key=score)
