"""OpenCV-based object tracking."""

import cv2
import numpy as np


def init_tracker(bbox, frame):
    """
    Initialize CSRT tracker for the given bbox.
    CSRT gives good accuracy; use KCF for faster but less accurate.
    """
    try:
        tracker = cv2.legacy.TrackerCSRT_create()
    except AttributeError:
        tracker = cv2.TrackerCSRT_create()
    tracker.init(frame, bbox)
    return tracker


def update_tracker(tracker, frame):
    """
    Update tracker with new frame.
    Returns (success, bbox) where bbox is (x, y, w, h).
    """
    success, bbox = tracker.update(frame)
    if success:
        bbox = tuple(int(v) for v in bbox)
    return success, bbox


def bbox_xyxy_to_xywh(bbox):
    """Convert (x1,y1,x2,y2) to (x,y,w,h)."""
    x1, y1, x2, y2 = bbox
    return (x1, y1, x2 - x1, y2 - y1)


def bbox_xywh_to_xyxy(bbox):
    """Convert (x,y,w,h) to (x1,y1,x2,y2)."""
    x, y, w, h = bbox
    return (x, y, x + w, y + h)
