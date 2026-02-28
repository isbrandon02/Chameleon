#!/usr/bin/env python3
"""
object_replace.py — Realistic Object Replacement in Video

Replaces a stationary object (e.g., Coke can) with an actual product image
(e.g., Heineken bottle photo) using precise segmentation and compositing.

Pipeline:
    1. YOLOv8      — detect object bounding box
    2. SAM         — precise segmentation mask
    3. MiDaS       — depth estimation for scale refinement (optional)
    4. Motion      — CSRT tracker for per-frame bbox (camera/object movement)
    5. LaMa        — AI inpainting for photorealistic object removal (or OpenCV fallback)
    6. OpenCV      — homography, composite, no background blur
    7. FFmpeg      — reassemble with original audio

Usage:
    python3 object_replace.py \\
        --video video.mp4 \\
        --replacement heineken.png \\
        --target-class cup \\
        --output output.mp4

Requirements:
    pip install ultralytics opencv-python numpy torch torchvision
    pip install segment-anything
    FFmpeg must be installed.
"""

from __future__ import annotations

import argparse
from typing import Callable
import os
import subprocess
import sys
import tempfile
import urllib.request

import cv2
import numpy as np
import torch
from PIL import Image


# ---------------------------------------------------------------------------
# Background removal (optional)
# ---------------------------------------------------------------------------

def remove_background(img_bgra: np.ndarray) -> np.ndarray:
    """Remove background from image. Returns BGRA with transparent background. Falls back to input if rembg unavailable."""
    try:
        from rembg import remove as rembg_remove
    except ImportError:
        return img_bgra

    pil = Image.fromarray(cv2.cvtColor(img_bgra[:, :, :3], cv2.COLOR_BGR2RGB))
    out = rembg_remove(pil)
    out_rgba = np.array(out)
    if out_rgba.shape[2] == 4:
        out_bgra = cv2.cvtColor(out_rgba[:, :, :3], cv2.COLOR_RGB2BGR)
        out_bgra = np.concatenate([out_bgra, out_rgba[:, :, 3:4]], axis=2)
    else:
        out_bgra = cv2.cvtColor(out_rgba, cv2.COLOR_RGB2BGR)
        out_bgra = np.concatenate([out_bgra, np.full((*out_bgra.shape[:2], 1), 255, dtype=np.uint8)], axis=2)
    return out_bgra


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAM_CHECKPOINT = "sam_vit_b_01ec64.pth"
SAM_MODEL_TYPE = "vit_b"
SAM_URL = "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth"


# ---------------------------------------------------------------------------
# Motion Tracking (CSRT)
# ---------------------------------------------------------------------------

def create_tracker() -> cv2.Tracker | None:
    """Create CSRT tracker; fallback to KCF if CSRT unavailable."""
    try:
        return cv2.legacy.TrackerCSRT_create()
    except AttributeError:
        try:
            return cv2.TrackerKCF_create()
        except AttributeError:
            return None


def init_and_track_bbox(
    tracker: cv2.Tracker | None,
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
    initialized: bool,
) -> tuple[bool, tuple[int, int, int, int]]:
    """
    Initialize tracker on first frame, update on subsequent frames.
    Returns (initialized, bbox). bbox is (x, y, w, h).
    """
    x, y, w, h = bbox
    fh, fw = frame.shape[:2]
    # Clamp bbox to frame
    x = max(0, min(x, fw - 1))
    y = max(0, min(y, fh - 1))
    w = max(1, min(w, fw - x))
    h = max(1, min(h, fh - y))
    roi = (x, y, w, h)

    if tracker is None:
        return True, roi

    if not initialized:
        tracker.init(frame, roi)
        return True, roi

    ok, new_roi = tracker.update(frame)
    if ok:
        rx, ry, rw, rh = (int(v) for v in new_roi)
        rx = max(0, min(rx, fw - 1))
        ry = max(0, min(ry, fh - 1))
        rw = max(1, min(rw, fw - rx))
        rh = max(1, min(rh, fh - ry))
        return True, (rx, ry, rw, rh)
    return False, roi  # Fallback to last known


# ---------------------------------------------------------------------------
# Depth Estimation (MiDaS)
# ---------------------------------------------------------------------------

_midas_model = None
_midas_transform = None


def _get_midas():
    """Lazy load MiDaS depth model."""
    global _midas_model, _midas_transform
    if _midas_model is not None:
        return _midas_model, _midas_transform
    try:
        import torch
        _midas_model = torch.hub.load("intel-isl/MiDaS", "MiDaS_small", trust_repo=True)
        _midas_model.eval()
        device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
        _midas_model.to(device)
        _midas_transform = torch.hub.load("intel-isl/MiDaS", "transforms").small_transform
        return _midas_model, _midas_transform
    except Exception as e:
        print(f"[warn] MiDaS depth unavailable: {e}")
        return None, None


def get_depth_map(frame: np.ndarray) -> np.ndarray | None:
    """Get MiDaS depth map (inverse depth). Returns float array same size as frame or None."""
    model, transform = _get_midas()
    if model is None:
        return None
    try:
        import torch
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        input_batch = transform(img_rgb).to(next(model.parameters()).device)
        if input_batch.dim() == 3:
            input_batch = input_batch.unsqueeze(0)
        with torch.no_grad():
            pred = model(input_batch)
            pred = torch.nn.functional.interpolate(
                pred.unsqueeze(1),
                size=frame.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()
        return pred.cpu().numpy()
    except Exception as e:
        print(f"[warn] MiDaS inference failed: {e}")
        return None


def depth_scale_factor(depth_map: np.ndarray, bbox: tuple[int, int, int, int], frame_shape: tuple[int, int]) -> float:
    """
    Use depth to refine scale. Conservative range (0.95–1.05) for subtle realism.
    """
    try:
        x, y, w, h = bbox
        fh, fw = frame_shape[:2]
        obj_depth = float(np.median(depth_map[max(0, y) : min(fh, y + h), max(0, x) : min(fw, x + w)]))
        margin = 40
        top = depth_map[:margin, :].mean() if margin < fh else obj_depth
        bottom = depth_map[-margin:, :].mean() if margin < fh else obj_depth
        left = depth_map[:, :margin].mean() if margin < fw else obj_depth
        right = depth_map[:, -margin:].mean() if margin < fw else obj_depth
        scene_depth = np.median([top, bottom, left, right])
        if scene_depth <= 1e-6:
            return 1.0
        ratio = obj_depth / scene_depth
        return float(np.clip(ratio, 0.95, 1.05))  # Conservative — avoid shrinking
    except Exception:
        return 1.0


# ---------------------------------------------------------------------------
# Homography / Perspective Warp
# ---------------------------------------------------------------------------

def compute_perspective_quad(
    bbox: tuple[int, int, int, int],
    depth_map: np.ndarray | None,
) -> np.ndarray:
    """
    Compute 4-point quad (bbox-relative) from depth. If depth suggests perspective
    (top further), top edge is shorter. Returns dst_pts (4x2) in bbox coords [0..w, 0..h].
    """
    x, y, w, h = bbox
    dst = np.float32([[0, 0], [w, 0], [w, h], [0, h]])

    if depth_map is not None:
        try:
            roi = depth_map[max(0, y) : min(y + h, depth_map.shape[0]), max(0, x) : min(x + w, depth_map.shape[1])]
            if roi.size > 10:
                top_depth = np.median(roi[: max(1, roi.shape[0] // 4), :])
                bottom_depth = np.median(roi[-max(1, roi.shape[0] // 4) :, :])
                if top_depth > 1e-6 and bottom_depth > 1e-6:
                    ratio = bottom_depth / top_depth
                    if 0.85 < ratio < 1.15 and abs(ratio - 1.0) > 0.02:
                        shift = w * 0.04 * (1 - ratio)
                        dst[0, 0] += shift
                        dst[1, 0] -= shift
                        dst[2, 0] -= shift
                        dst[3, 0] += shift
        except Exception:
            pass
    return dst


def warp_replacement_perspective(
    replacement_bgra: np.ndarray,
    dst_quad: np.ndarray,
    out_w: int,
    out_h: int,
) -> np.ndarray:
    """
    Warp replacement to match perspective. src = replacement rect, dst = dst_quad (bbox coords).
    Returns warped BGRA (out_w x out_h).
    """
    rh, rw = replacement_bgra.shape[:2]
    src_quad = np.float32([[0, 0], [rw, 0], [rw, rh], [0, rh]])
    H, _ = cv2.findHomography(src_quad, dst_quad, cv2.RANSAC, 5.0)
    if H is None:
        return cv2.resize(replacement_bgra, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
    return cv2.warpPerspective(
        replacement_bgra,
        H,
        (out_w, out_h),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )


# ---------------------------------------------------------------------------
# 1. Object Detection (YOLOv8)
# ---------------------------------------------------------------------------

def detect_object(
    frame: np.ndarray,
    target_class: str = "bottle",
) -> tuple[int, int, int, int] | None:
    """Detect target object. Returns (x, y, w, h) or None."""
    from ultralytics import YOLO

    # For bottles (e.g. coke), try bottle then cup then wine glass (YOLO can misclassify)
    fallback_classes = ["bottle", "cup", "wine glass"] if target_class == "bottle" else [target_class]

    model = YOLO("yolov8n.pt")
    results = model(frame, verbose=False)[0]

    best_box, best_conf, best_class = None, 0.0, None
    for try_class in fallback_classes:
        target_ids = [k for k, v in results.names.items() if v == try_class]
        if not target_ids:
            continue
        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            if cls_id in target_ids and conf > best_conf:
                best_conf = conf
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                best_box = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))
                best_class = try_class
        if best_box:
            break

    if best_box:
        print(f"[info] Detected '{best_class}' at {best_box} (conf={best_conf:.2f})")
    else:
        print(f"[warn] No bottle/cup detected.")
    return best_box


# ---------------------------------------------------------------------------
# 2. Mask Refinement (SAM)
# ---------------------------------------------------------------------------

def _ensure_sam_checkpoint() -> str:
    if os.path.isfile(SAM_CHECKPOINT):
        return SAM_CHECKPOINT
    print("[info] Downloading SAM checkpoint...")
    urllib.request.urlretrieve(SAM_URL, SAM_CHECKPOINT)
    print("[info] SAM checkpoint downloaded.")
    return SAM_CHECKPOINT


def refine_mask(
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> np.ndarray:
    """Precise pixel mask via SAM. Returns uint8 (255=object, 0=bg)."""
    try:
        from segment_anything import SamPredictor, sam_model_registry
    except ImportError:
        print("[warn] segment-anything not installed — rectangular mask.")
        return _rect_mask(frame, bbox)

    checkpoint = _ensure_sam_checkpoint()
    device = "mps" if torch.backends.mps.is_available() else "cpu"

    sam = sam_model_registry[SAM_MODEL_TYPE](checkpoint=checkpoint)
    sam.to(device)
    predictor = SamPredictor(sam)
    predictor.set_image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    x, y, w, h = bbox
    masks, scores, _ = predictor.predict(
        box=np.array([[x, y, x + w, y + h]]),
        multimask_output=True,
    )
    best_idx = int(np.argmax(scores))
    mask = (masks[best_idx] * 255).astype(np.uint8)
    print(f"[info] SAM mask refined (score={scores[best_idx]:.3f})")
    return mask


def _rect_mask(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = bbox
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    mask[y : y + h, x : x + w] = 255
    return mask


# ---------------------------------------------------------------------------
# 3. Inpaint Background (remove original object)
# ---------------------------------------------------------------------------

def _inpaint_lama(frame: np.ndarray, dilated_mask: np.ndarray) -> np.ndarray | None:
    """
    LaMa (Large Mask Inpainting) — open-source AI, photorealistic fill.
    Only modifies masked region; background untouched. No blur.
    """
    try:
        from simple_lama_inpainting import SimpleLama
        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        pil_mask = Image.fromarray(dilated_mask)
        lama = SimpleLama()
        result = lama(pil_img, pil_mask)
        return cv2.cvtColor(np.array(result), cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"[warn] LaMa inpainting unavailable ({e}), falling back to OpenCV")
        return None


def inpaint_background(
    frame: np.ndarray,
    mask: np.ndarray,
    bbox: tuple[int, int, int, int],
    use_lama: bool = True,
) -> np.ndarray:
    """
    Remove original object — LaMa AI (photorealistic) or OpenCV fallback.
    Mask-only: only inpaint region is modified. No background blur.
    """
    x, y, w, h = bbox
    fh, fw = frame.shape[:2]

    full_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    full_mask[y : y + h, x : x + w] = 255
    merged = np.maximum(mask, full_mask)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    dilated = cv2.dilate(merged, kernel, iterations=2)

    shadow_h = int(h * 0.6)
    sy1 = min(y + h, fh - 1)
    sy2 = min(y + h + shadow_h, fh)
    sx1 = max(x - int(w * 0.2), 0)
    sx2 = min(x + w + int(w * 0.2), fw)
    if sy2 > sy1:
        dilated[sy1:sy2, sx1:sx2] = 255

    dilated = cv2.dilate(dilated, kernel, iterations=1)

    if use_lama:
        result = _inpaint_lama(frame, dilated)
        if result is not None:
            print("[info] Background inpainted with LaMa (AI, photorealistic).")
            return result

    inpainted = cv2.inpaint(frame, dilated, inpaintRadius=3, flags=cv2.INPAINT_NS)
    print("[info] Background inpainted (OpenCV fallback).")
    return inpainted


# ---------------------------------------------------------------------------
# 4. Realistic Color Match (Stock Image → Scene)
# ---------------------------------------------------------------------------

def _color_transfer_reinhard(
    src: np.ndarray,
    tgt: np.ndarray,
    vis_mask: np.ndarray,
    strength: float = 0.88,
) -> np.ndarray:
    """
    Reinhard-style color transfer: match mean and std of LAB channels.
    Strong match so product looks shot in scene — lighting, color temp, intensity.
    """
    if not vis_mask.any():
        return src.copy()

    src_lab = cv2.cvtColor(src, cv2.COLOR_BGR2LAB).astype(np.float64)
    tgt_lab = cv2.cvtColor(tgt, cv2.COLOR_BGR2LAB).astype(np.float64)

    result = src_lab.copy()
    for c in range(3):
        tgt_vals = tgt_lab[:, :, c].flatten()
        src_vals = src_lab[:, :, c][vis_mask]

        tgt_mean, tgt_std = tgt_vals.mean(), max(tgt_vals.std(), 1e-6)
        src_mean, src_std = src_vals.mean(), max(src_vals.std(), 1e-6)

        # Transfer: (src - src_mean) * (tgt_std/src_std) + tgt_mean
        transferred = (src_lab[:, :, c] - src_mean) * (tgt_std / src_std) + tgt_mean
        # Blend with original
        result[:, :, c][vis_mask] = (
            strength * transferred[vis_mask] + (1 - strength) * src_lab[:, :, c][vis_mask]
        )

    result = np.clip(result, 0, 255).astype(np.uint8)
    return cv2.cvtColor(result, cv2.COLOR_LAB2BGR)


def _add_matching_grain(product_bgr: np.ndarray, scene_bgr: np.ndarray, vis_mask: np.ndarray) -> np.ndarray:
    """
    Add subtle grain to product to match scene noise — avoids sterile AI look.
    """
    gray_scene = cv2.cvtColor(scene_bgr, cv2.COLOR_BGR2GRAY).astype(np.float64)
    # Estimate scene noise from high-frequency content (Laplacian variance)
    lap = cv2.Laplacian(gray_scene, cv2.CV_64F, ksize=3)
    scene_noise = float(np.std(lap))
    scene_noise = max(0.8, min(3.5, scene_noise * 0.15))
    np.random.seed(42)
    h, w = product_bgr.shape[:2]
    noise = np.random.randn(h, w).astype(np.float32) * scene_noise
    out = product_bgr.astype(np.float32).copy()
    for c in range(3):
        out[:, :, c] = np.clip(out[:, :, c] + noise * vis_mask.astype(np.float32), 0, 255)
    return out.astype(np.uint8)


def _add_contact_shadow(
    frame: np.ndarray,
    ox: int,
    oy: int,
    rw: int,
    rh: int,
    alpha: np.ndarray,
    strength: float = 0.12,
) -> None:
    """
    Contact shadow + ambient occlusion — physically grounded, no floating.
    """
    fh, fw = frame.shape[:2]
    clip_h = min(rh, fh - oy)
    clip_w = min(rw, fw - ox)
    if clip_h <= 0 or clip_w <= 0:
        return

    # Scale with object size — works for any distance
    size_ref = max(rh, rw, 10)
    blur_k = max(5, min(25, size_ref // 6))
    blur_k = blur_k | 1  # odd

    foot_h = max(2, int(clip_h * 0.25))
    foot = alpha[-foot_h:, :].copy()
    foot = np.max(foot, axis=0, keepdims=True)
    foot = np.tile(foot, (foot_h, 1))
    foot = cv2.GaussianBlur(foot, (blur_k, blur_k), 0)
    foot = np.clip(foot, 0, 1)

    roi = frame[oy + clip_h - foot_h : oy + clip_h, ox : ox + clip_w].astype(np.float32)
    darken = 1 - foot[:, :, np.newaxis] * strength
    darkened = roi * darken
    frame[oy + clip_h - foot_h : oy + clip_h, ox : ox + clip_w] = np.clip(
        darkened, 0, 255
    ).astype(np.uint8)


def _add_cast_shadow(
    frame: np.ndarray,
    ox: int,
    oy: int,
    rw: int,
    rh: int,
    alpha: np.ndarray,
    strength: float = 0.10,
) -> None:
    """
    Cast shadow: adapts to object size — works for any distance.
    """
    fh, fw = frame.shape[:2]
    clip_h = min(rh, fh - oy)
    clip_w = min(rw, fw - ox)
    if clip_h <= 0 or clip_w <= 0:
        return

    shadow_h = min(int(rh * 0.35), fh - (oy + clip_h))
    if shadow_h <= 0:
        return

    sy1 = oy + clip_h
    sy2 = min(sy1 + shadow_h, fh)
    sx1 = max(ox - int(rw * 0.15), 0)
    sx2 = min(ox + clip_w + int(rw * 0.15), fw)

    sh, sw = sy2 - sy1, sx2 - sx1
    foot = alpha[-max(1, clip_h // 4) :, :]
    foot = np.max(foot, axis=0)
    mask_sh = cv2.resize(
        foot.astype(np.float32).reshape(1, -1), (sw, sh), interpolation=cv2.INTER_LINEAR
    )
    blur_k = max(11, min(41, max(rh, rw) // 4))
    blur_k = blur_k | 1
    mask_sh = cv2.GaussianBlur(mask_sh, (blur_k, blur_k), 0)
    mask_sh = np.clip(mask_sh, 0, 1)

    roi = frame[sy1:sy2, sx1:sx2].astype(np.float32)
    darken = 1 - mask_sh[:, :, np.newaxis] * strength
    frame[sy1:sy2, sx1:sx2] = np.clip(roi * darken, 0, 255).astype(np.uint8)


def _detect_surface_shear(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> float:
    """
    Detect if object is against a slanted wall — returns shear factor for alignment.
    Product forms against wall on the side.
    """
    try:
        x, y, w, h = bbox
        fh, fw = frame.shape[:2]
        pad = max(w, h) // 2
        left_roi = frame[max(0, y - pad) : min(fh, y + h + pad), max(0, x - w) : max(1, x)]
        right_roi = frame[max(0, y - pad) : min(fh, y + h + pad), min(fw - 1, x + w) : min(fw, x + w + w)]
        gray_left = cv2.cvtColor(left_roi, cv2.COLOR_BGR2GRAY) if left_roi.size > 100 else None
        gray_right = cv2.cvtColor(right_roi, cv2.COLOR_BGR2GRAY) if right_roi.size > 100 else None
        edges_left = cv2.Canny(gray_left, 50, 150) if gray_left is not None else None
        edges_right = cv2.Canny(gray_right, 50, 150) if gray_right is not None else None
        lines_left = cv2.HoughLinesP(edges_left, 1, np.pi / 180, 20, minLineLength=15, maxLineGap=5) if edges_left is not None and edges_left.size > 0 else None
        lines_right = cv2.HoughLinesP(edges_right, 1, np.pi / 180, 20, minLineLength=15, maxLineGap=5) if edges_right is not None and edges_right.size > 0 else None

        def mean_angle(lines):
            if lines is None or len(lines) == 0:
                return None
            angles = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.degrees(np.arctan2(y2 - y1, x2 - x1 + 1e-6))
                if 10 < abs(angle) < 80:
                    angles.append(angle)
            return np.median(angles) if angles else None

        a_left = mean_angle(lines_left)
        a_right = mean_angle(lines_right)
        if a_left is not None:
            return 0.06 if a_left > 0 else -0.06
        if a_right is not None:
            return -0.06 if a_right > 0 else 0.06
    except Exception:
        pass
    return 0.0


def _compute_replacement_placement(
    replacement: np.ndarray,
    bbox: tuple[int, int, int, int],
    frame_h: int,
    frame_w: int,
    product_scale: float = 1.0,
    depth_scale: float = 1.0,
) -> tuple[int, int, int, int]:
    """
    Match scale and proportions. product_scale < 1 = smaller (advertisement).
    depth_scale from MiDaS refines for distance. Returns (ox, oy, rw, rh).
    """
    x, y, w, h = bbox
    repl_h, repl_w = replacement.shape[0], replacement.shape[1]

    # Scale: fit inside bbox, preserve aspect; product_scale + depth_scale
    scale = min(w / max(repl_w, 1), h / max(repl_h, 1)) * product_scale * depth_scale
    rw = int(repl_w * scale)
    rh = int(repl_h * scale)
    rw, rh = max(1, rw), max(1, rh)

    # Anchor bottom: object rests where original stood
    ox = x + (w - rw) // 2
    oy = y + h - rh
    ox = max(0, min(ox, frame_w - 1))
    oy = max(0, min(oy, frame_h - 1))
    rw = min(rw, frame_w - ox)
    rh = min(rh, frame_h - oy)
    rw, rh = max(1, rw), max(1, rh)
    return ox, oy, rw, rh


def realistic_composite(
    frame: np.ndarray,
    replacement_bgra: np.ndarray,
    bbox: tuple[int, int, int, int],
    mask: np.ndarray,
    scene_region: np.ndarray,
    placement: tuple[int, int, int, int] | None = None,
    depth_map: np.ndarray | None = None,
    depth_scale: float = 1.0,
    use_homography: bool = False,
) -> np.ndarray:
    """
    High-realism composite: scale, perspective (homography), lighting; no blur or haloing.
    depth_scale refines size; use_homography warps replacement to match perspective.
    """
    x, y, w, h = bbox
    fh, fw = frame.shape[:2]

    if placement is None:
        ox, oy, rw, rh = _compute_replacement_placement(
            replacement_bgra, bbox, fh, fw, depth_scale=depth_scale
        )
    else:
        ox, oy, rw, rh = placement

    # Homography perspective warp (depth-based quad) or affine resize
    if use_homography and depth_map is not None:
        dst_quad = compute_perspective_quad(bbox, depth_map)
        resized = warp_replacement_perspective(replacement_bgra, dst_quad, w, h)
        # Resize to rw x rh for placement (placement uses ox, oy, rw, rh)
        if (resized.shape[1], resized.shape[0]) != (rw, rh):
            resized = cv2.resize(resized, (rw, rh), interpolation=cv2.INTER_LANCZOS4)
    else:
        resized = cv2.resize(
            replacement_bgra, (rw, rh), interpolation=cv2.INTER_LANCZOS4
        )

    # Surface alignment: if object is against slanted wall, shear to form against it
    shear = _detect_surface_shear(frame, bbox)
    if abs(shear) > 0.01:
        # Shear: top moves horizontally, bottom stays fixed (anchor base)
        M = np.float32([[1, 0, 0], [shear, 1, 0]])
        resized = cv2.warpAffine(
            resized,
            M,
            (rw, rh),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )

    # Visibility mask (product pixels)
    if resized.shape[2] == 4:
        vis_mask = resized[:, :, 3] > 32
        bgr = resized[:, :, :3]
    else:
        vis_mask = np.ones((rh, rw), dtype=bool)
        bgr = resized.copy()

    # Resize scene region to match replacement size
    scene_small = cv2.resize(scene_region, (rw, rh), interpolation=cv2.INTER_AREA)

    # Lighting match: full strength — product must look shot in scene
    color_matched = _color_transfer_reinhard(bgr, scene_small, vis_mask, strength=0.88)
    # Grain matching — scene has noise; product must match or looks AI
    color_matched = _add_matching_grain(color_matched, scene_small, vis_mask)

    # Alpha: replacement fully covers original — dilated mask + vis_mask, no gaps
    mask_roi = mask[y : y + h, x : x + w]
    mask_resized = cv2.resize(mask_roi, (rw, rh), interpolation=cv2.INTER_LINEAR)
    k = max(7, min(21, min(rh, rw) // 5)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask_resized = cv2.dilate(
        (mask_resized > 127).astype(np.uint8) * 255, kernel
    ).astype(np.float32) / 255.0
    alpha = mask_resized * vis_mask.astype(np.float32)
    # Minimal feather — no haloing, crisp edges, no artificial blur
    feather = max(3, min(11, max(rh, rw) // 12)) | 1
    alpha = cv2.GaussianBlur(alpha, (feather, feather), 0)
    alpha = np.clip(alpha, 0, 1)

    # Clamp to frame bounds
    clip_h = min(rh, fh - oy)
    clip_w = min(rw, fw - ox)
    color_matched = color_matched[:clip_h, :clip_w]
    alpha = alpha[:clip_h, :clip_w]

    # Contact shadow + cast shadow — physically grounded, realistic
    _add_contact_shadow(frame, ox, oy, rw, rh, alpha, strength=0.12)
    _add_cast_shadow(frame, ox, oy, rw, rh, alpha, strength=0.10)

    # Composite: seamless blend replacement onto frame
    roi = frame[oy : oy + clip_h, ox : ox + clip_w].astype(np.float32)
    alpha3 = alpha[:, :, np.newaxis]
    blended = alpha3 * color_matched + (1 - alpha3) * roi
    frame[oy : oy + clip_h, ox : ox + clip_w] = np.clip(blended, 0, 255).astype(np.uint8)

    return frame


# Legacy alias for compatibility
def composite_replacement(
    frame: np.ndarray,
    replacement_bgra: np.ndarray,
    bbox: tuple[int, int, int, int],
    mask: np.ndarray | None = None,
    scene_region: np.ndarray | None = None,
) -> np.ndarray:
    """Composite replacement; uses realistic_composite when mask/scene provided."""
    x, y, w, h = bbox
    fh, fw = frame.shape[:2]
    pad = 30
    sy1, sy2 = max(y - pad, 0), min(y + h + pad, fh)
    sx1, sx2 = max(x - pad, 0), min(x + w + pad, fw)
    scene = scene_region if scene_region is not None else frame[sy1:sy2, sx1:sx2]
    m = mask if mask is not None else np.ones((h, w), dtype=np.uint8) * 255
    return realistic_composite(frame, replacement_bgra, bbox, m, scene, placement=None)


# ---------------------------------------------------------------------------
# 6. Video Pipeline
# ---------------------------------------------------------------------------

def render_video(
    video_path: str,
    replacement_path: str,
    output_path: str = "output.mp4",
    target_class: str = "bottle",
    use_sam: bool = True,
    padding: int = 0,
    product_scale: float = 1.0,
    use_tracking: bool = True,
    use_depth: bool = True,
    use_homography: bool = True,
    use_lama: bool = True,
    progress_callback: Callable[[int, str], None] | None = None,
) -> None:
    """
    Full pipeline:
        1. Detect object (YOLOv8)
        2. SAM mask refinement
        3. Optional MiDaS depth for scale
        4. Optional CSRT motion tracking (per-frame bbox)
        5. Inpaint + composite with homography
        6. FFmpeg export
    """
    if not os.path.isfile(video_path):
        sys.exit(f"[error] Video not found: {video_path}")
    if not os.path.isfile(replacement_path):
        sys.exit(f"[error] Replacement image not found: {replacement_path}")

    # --- Open video ---
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        sys.exit(f"[error] Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[info] Video: {frame_w}x{frame_h} @ {fps:.1f} fps, {total_frames} frames")

    ret, first_frame = cap.read()
    if not ret:
        sys.exit("[error] Cannot read first frame.")

    def _progress(pct: int, msg: str) -> None:
        if progress_callback:
            progress_callback(pct, msg)
        print(f"[info] {msg}")

    # --- Step 1: Detect ---
    print("\n=== Step 1: Object Detection (YOLOv8) ===")
    _progress(1, "Detecting bottle/cup...")
    bbox = detect_object(first_frame, target_class)
    if bbox is None:
        sys.exit("[error] Detection failed. Try bottle, cup, or wine glass.")
    x, y, w, h = bbox

    # Apply padding to bbox (expand or shrink)
    x = max(x - padding, 0)
    y = max(y - padding, 0)
    w = min(w + padding * 2, frame_w - x)
    h = min(h + padding * 2, frame_h - y)
    bbox = (x, y, w, h)
    if padding != 0:
        print(f"[info] Padded bbox: {bbox}")

    # --- Step 2: Segment ---
    print("\n=== Step 2: Mask Refinement (SAM) ===")
    _progress(3, "Segmenting object...")
    mask = refine_mask(first_frame, bbox) if use_sam else _rect_mask(first_frame, bbox)

    # --- Step 2.5: MiDaS depth (optional) ---
    depth_map: np.ndarray | None = None
    depth_scale = 1.0
    if use_depth:
        _progress(4, "Estimating depth (MiDaS)...")
        depth_map = get_depth_map(first_frame)
        if depth_map is not None:
            depth_scale = depth_scale_factor(depth_map, bbox, (frame_h, frame_w))
            print(f"[info] Depth scale factor: {depth_scale:.3f}")

    # --- Step 3: Inpaint background (object + shadow) ---
    print("\n=== Step 3: Remove Original Object + Shadow ===")
    _progress(5, "Removing original object and shadow...")
    clean_plate = inpaint_background(first_frame, mask, bbox, use_lama=use_lama)

    # --- Step 4: Load replacement and composite ---
    print("\n=== Step 4: Composite Replacement ===")
    _progress(7, "Compositing replacement...")
    replacement = cv2.imread(replacement_path, cv2.IMREAD_UNCHANGED)
    if replacement is None:
        sys.exit(f"[error] Cannot load: {replacement_path}")

    if replacement.shape[2] == 3:
        alpha_ch = np.full((replacement.shape[0], replacement.shape[1], 1), 255, dtype=np.uint8)
        replacement = np.concatenate([replacement, alpha_ch], axis=2)

    _progress(6, "Removing background from product...")
    replacement = remove_background(replacement)
    if replacement.shape[2] == 3:
        replacement = np.concatenate([replacement, np.full((*replacement.shape[:2], 1), 255, dtype=np.uint8)], axis=2)

    print(f"[info] Replacement image: {replacement.shape[1]}x{replacement.shape[0]}, "
          f"alpha={'yes' if replacement.shape[2] == 4 else 'no'}")
    print("[info] Creating realistic composite (preserve proportions, color-match scene)...")

    # Placement: product scaled (depth + advertisement), anchored to surface
    ox, oy, rw, rh = _compute_replacement_placement(
        replacement, bbox, frame_h, frame_w,
        product_scale=product_scale, depth_scale=depth_scale,
    )

    # Build the composited first frame (with homography if enabled)
    composited = clean_plate.copy()
    scene_region = first_frame[max(y - 40, 0) : min(y + h + 40, frame_h), max(x - 40, 0) : min(x + w + 40, frame_w)]
    composited = realistic_composite(
        composited, replacement, bbox, mask, scene_region,
        placement=(ox, oy, rw, rh),
        depth_map=depth_map, depth_scale=depth_scale, use_homography=use_homography,
    )

    # --- Motion tracking setup ---
    tracker = create_tracker() if use_tracking else None
    tracker_initialized = False

    # Patch region: cover full original bbox + margin so replacement completely replaces
    margin = 48
    py1 = max(min(oy, y) - margin, 0)
    py2 = min(max(oy + rh, y + h) + margin, frame_h)
    px1 = max(min(ox, x) - margin, 0)
    px2 = min(max(ox + rw, x + w) + margin, frame_w)

    patch = composited[py1:py2, px1:px2].copy()

    # Replace ENTIRE patch — no original frame bleed-through
    ph, pw = py2 - py1, px2 - px1
    blend = np.ones((ph, pw), dtype=np.float32)
    # Thin feather only at outer edge to avoid hard cutoff
    feather = 5
    blend[0:feather, :] *= np.linspace(0, 1, feather)[:, np.newaxis]
    blend[-feather:, :] *= np.linspace(1, 0, feather)[:, np.newaxis]
    blend[:, 0:feather] *= np.linspace(0, 1, feather)[np.newaxis, :]
    blend[:, -feather:] *= np.linspace(1, 0, feather)[np.newaxis, :]
    patch_blend = np.clip(blend, 0, 1)

    # --- Step 5: Apply to all frames ---
    print(f"\n=== Step 5: Processing {total_frames} Frames ===")
    _progress(10, f"Processing video frames (0/{total_frames})...")
    tmp_dir = tempfile.mkdtemp()
    tmp_video = os.path.join(tmp_dir, "tmp_no_audio.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(tmp_video, fourcc, fps, (frame_w, frame_h))

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    frame_idx = 0
    current_bbox = bbox  # For tracking fallback

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if tracker is not None:
            # Per-frame: track, inpaint, composite (motion-aware)
            tracker_initialized, current_bbox = init_and_track_bbox(
                tracker, frame, current_bbox, tracker_initialized
            )
            tx, ty, tw, th = current_bbox
            # Warp mask from original (w,h) to current (tw,th), place in full-frame
            mask_roi = cv2.resize(mask, (tw, th), interpolation=cv2.INTER_LINEAR)
            mask_roi = (mask_roi > 127).astype(np.uint8) * 255
            mask_full = np.zeros(frame.shape[:2], dtype=np.uint8)
            sy1, sy2 = max(0, ty), min(frame_h, ty + th)
            sx1, sx2 = max(0, tx), min(frame_w, tx + tw)
            my1, my2 = max(0, -ty), min(th, frame_h - ty)
            mx1, mx2 = max(0, -tx), min(tw, frame_w - tx)
            if sy2 > sy1 and sx2 > sx1 and my2 > my1 and mx2 > mx1:
                mask_full[sy1:sy2, sx1:sx2] = mask_roi[my1:my2, mx1:mx2]
            # Inpaint frame at tracked bbox
            frame_inpainted = inpaint_background(frame.copy(), mask_full, current_bbox, use_lama=use_lama)
            # Compute placement for current bbox (use depth_scale from first frame)
            ox_t, oy_t, rw_t, rh_t = _compute_replacement_placement(
                replacement, current_bbox, frame_h, frame_w,
                product_scale=product_scale, depth_scale=depth_scale,
            )
            scene_t = frame_inpainted[max(ty - 40, 0) : min(ty + th + 40, frame_h), max(tx - 40, 0) : min(tx + tw + 40, frame_w)]
            # Depth map per frame would be slow; use first-frame depth for homography quad
            dm = depth_map if frame_idx == 0 else None
            frame_out = realistic_composite(
                frame_inpainted, replacement, current_bbox, mask_full, scene_t,
                placement=(ox_t, oy_t, rw_t, rh_t),
                depth_map=dm, depth_scale=depth_scale, use_homography=use_homography and dm is not None,
            )
        else:
            # Static: blend pre-computed patch
            roi = frame[py1:py2, px1:px2].astype(np.float32)
            patch_f = patch.astype(np.float32)
            blend3 = patch_blend[:, :, np.newaxis]
            blended = blend3 * patch_f + (1 - blend3) * roi
            frame_out = frame.copy()
            frame_out[py1:py2, px1:px2] = blended.astype(np.uint8)

        writer.write(frame_out)
        frame_idx += 1

        if frame_idx % 15 == 0 or frame_idx == total_frames:
            pct = int(10 + (frame_idx / total_frames) * 80)  # 10–90%
            _progress(pct, f"Processing video frames ({frame_idx}/{total_frames})...")

    cap.release()
    writer.release()

    # --- Step 6: FFmpeg ---
    print("\n=== Step 6: FFmpeg Audio Mux ===")
    _progress(92, "Adding audio to video...")
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", tmp_video,
        "-i", video_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac",
        "-map", "0:v:0", "-map", "1:a:0?",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[error] FFmpeg failed:\n{result.stderr}")
        sys.exit(1)

    os.remove(tmp_video)
    os.rmdir(tmp_dir)
    _progress(100, "Done! Video ready.")
    print(f"\n[done] Output: {output_path}")


# ---------------------------------------------------------------------------
# Natural poster region detection
# ---------------------------------------------------------------------------

def find_natural_poster_region(
    frame: np.ndarray,
    logo_aspect: float,
    min_pct: float = 15,
    max_pct: float = 45,
) -> tuple[float, float, float, float]:
    """
    Find natural wall/blank space for logo. Low-variance regions = likely wall.
    Adapts to logo aspect: column logos get taller narrower region.
    Returns (x_pct, y_pct, w_pct, h_pct).
    """
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame

    best_score = -1
    best_region = (30, 15, 40, 30)

    # Candidate sizes — adapt to logo shape
    if logo_aspect > 1.5:  # column: taller, narrower
        candidates = [(20, 25), (18, 28), (22, 22), (25, 20)]
    elif logo_aspect < 0.7:  # wide banner
        candidates = [(35, 18), (40, 15), (30, 20)]
    else:
        candidates = [(30, 25), (35, 22), (40, 20), (25, 28)]

    for cw_pct, ch_pct in candidates:
        cw = max(int(w * cw_pct / 100), 20)
        ch = max(int(h * ch_pct / 100), 20)
        for y in range(0, h - ch, max(1, ch // 3)):
            for x in range(0, w - cw, max(1, cw // 3)):
                roi = gray[y : y + ch, x : x + cw]
                var = roi.var()
                if var < 800 and roi.size > 0:
                    score = cw * ch / (1 + var)
                    if score > best_score:
                        best_score = score
                        best_region = (
                            100 * x / w,
                            100 * y / h,
                            100 * cw / w,
                            100 * ch / h,
                        )

    return best_region


# ---------------------------------------------------------------------------
# Poster / Logo Placement (Product placement on wall)
# ---------------------------------------------------------------------------

def apply_logo_poster(
    video_path: str,
    logo_path: str,
    output_path: str = "output.mp4",
    poster_region: tuple[float, float, float, float] | None = None,
    auto_region: bool = True,
    progress_callback: Callable[[int, str], None] | None = None,
) -> None:
    """
    Place a logo as a poster on a wall — product placement.
    poster_region: (x_pct, y_pct, w_pct, h_pct) or None for auto.
    auto_region: find natural wall space when poster_region is None.
    Logo gets background removed, color-matched, seamless blend.
    Column logos get taller/narrower region.
    """
    if not os.path.isfile(video_path):
        sys.exit(f"[error] Video not found: {video_path}")
    if not os.path.isfile(logo_path):
        sys.exit(f"[error] Logo not found: {logo_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        sys.exit(f"[error] Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def _progress(pct: int, msg: str) -> None:
        if progress_callback:
            progress_callback(pct, msg)
        print(f"[info] {msg}")

    _progress(2, "Loading logo...")
    logo = cv2.imread(logo_path, cv2.IMREAD_UNCHANGED)
    if logo is None:
        sys.exit(f"[error] Cannot load: {logo_path}")
    if logo.shape[2] == 3:
        alpha_ch = np.full((logo.shape[0], logo.shape[1], 1), 255, dtype=np.uint8)
        logo = np.concatenate([logo, alpha_ch], axis=2)

    _progress(3, "Removing background...")
    logo = remove_background(logo)
    if logo.shape[2] == 3:
        logo = np.concatenate([logo, np.full((*logo.shape[:2], 1), 255, dtype=np.uint8)], axis=2)

    ret, first_frame = cap.read()
    if not ret:
        sys.exit("[error] Cannot read first frame.")

    logo_h, logo_w = logo.shape[:2]
    logo_aspect = logo_h / max(logo_w, 1)

    if poster_region is None and auto_region:
        _progress(4, "Finding natural space for poster...")
        poster_region = find_natural_poster_region(first_frame, logo_aspect)

    if poster_region is None:
        poster_region = (30, 15, 40, 30)
    x_pct, y_pct, w_pct, h_pct = poster_region

    px = int(frame_w * x_pct / 100)
    py = int(frame_h * y_pct / 100)
    pw = int(frame_w * w_pct / 100)
    ph = int(frame_h * h_pct / 100)
    px, py = max(0, px), max(0, py)
    pw = min(pw, frame_w - px)
    ph = min(ph, frame_h - py)
    pw, ph = max(10, pw), max(10, ph)

    _progress(5, "Placing poster on wall...")
    wall_region = first_frame[max(0, py - 20) : min(frame_h, py + ph + 20), max(0, px - 20) : min(frame_w, px + pw + 20)]

    # Column logo wrap: if tall/narrow, split into top+bottom and place side by side
    lh, lw = logo.shape[:2]
    margin = 0.08
    inner_w = int(pw * (1 - 2 * margin))
    inner_h = int(ph * (1 - 2 * margin))

    if logo_aspect > 2.0 and lh > lw * 2:  # column — wrap to 2 rows
        top = logo[: lh // 2, :]
        bot = logo[lh // 2 :, :]
        wrap_h = max(top.shape[0], bot.shape[0])
        wrap_w = top.shape[1] + bot.shape[1]
        wrapped = np.zeros((wrap_h, wrap_w, 4), dtype=np.uint8)
        wrapped[: top.shape[0], : top.shape[1]] = top
        wrapped[: bot.shape[0], top.shape[1] : top.shape[1] + bot.shape[1]] = bot
        logo = wrapped
        lh, lw = logo.shape[:2]
        logo_aspect = lh / max(lw, 1)

    scale = min(inner_w / max(lw, 1), inner_h / max(lh, 1))
    rw = int(lw * scale)
    rh = int(lh * scale)
    rw, rh = max(1, rw), max(1, rh)
    resized = cv2.resize(logo, (rw, rh), interpolation=cv2.INTER_LANCZOS4)

    ox = px + max(0, (pw - rw) // 2)
    oy = py + max(0, (ph - rh) // 2)
    ox = max(0, min(ox, frame_w - rw))
    oy = max(0, min(oy, frame_h - rh))

    vis_mask = resized[:, :, 3] > 32 if resized.shape[2] == 4 else np.ones((rh, rw), dtype=bool)
    if not vis_mask.any():
        vis_mask = np.ones((rh, rw), dtype=bool)
    bgr = resized[:, :, :3]
    scene_small = cv2.resize(wall_region, (rw, rh), interpolation=cv2.INTER_AREA)
    color_matched = _color_transfer_reinhard(bgr, scene_small, vis_mask, strength=0.6)

    if resized.shape[2] == 4 and vis_mask.any():
        alpha = (resized[:, :, 3].astype(np.float32) / 255.0) * vis_mask.astype(np.float32)
    else:
        alpha = np.ones((rh, rw), dtype=np.float32)
    alpha = cv2.GaussianBlur(alpha, (15, 15), 0)
    alpha = np.clip(alpha, 0, 1)
    alpha3 = alpha[:, :, np.newaxis]

    # Slight blend with wall so poster looks natural (ambient light)
    clip_h = min(rh, frame_h - oy)
    clip_w = min(rw, frame_w - ox)
    color_matched = color_matched[:clip_h, :clip_w]
    alpha3 = alpha3[:clip_h, :clip_w]

    patch = first_frame[oy : oy + clip_h, ox : ox + clip_w].copy()
    roi = patch.astype(np.float32)
    blended = alpha3 * color_matched + (1 - alpha3) * roi
    first_frame[oy : oy + clip_h, ox : ox + clip_w] = np.clip(blended, 0, 255).astype(np.uint8)

    # Build patch region for all frames
    margin_px = 24
    py1 = max(oy - margin_px, 0)
    py2 = min(oy + clip_h + margin_px, frame_h)
    px1 = max(ox - margin_px, 0)
    px2 = min(ox + clip_w + margin_px, frame_w)

    patch_full = first_frame[py1:py2, px1:px2].copy()
    blend_mask = np.zeros((py2 - py1, px2 - px1), dtype=np.float32)
    ly1, ly2 = oy - py1, oy - py1 + clip_h
    lx1, lx2 = ox - px1, ox - px1 + clip_w
    blend_mask[ly1:ly2, lx1:lx2] = 1.0
    blend_mask = cv2.GaussianBlur(blend_mask, (25, 25), 0)
    blend_mask = np.clip(blend_mask, 0, 1)[:, :, np.newaxis]

    _progress(10, f"Processing {total_frames} frames...")
    tmp_dir = tempfile.mkdtemp()
    tmp_video = os.path.join(tmp_dir, "tmp_no_audio.mp4")
    writer = cv2.VideoWriter(tmp_video, cv2.VideoWriter_fourcc(*"mp4v"), fps, (frame_w, frame_h))

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        roi_f = frame[py1:py2, px1:px2].astype(np.float32)
        blended_f = blend_mask * patch_full.astype(np.float32) + (1 - blend_mask) * roi_f
        frame[py1:py2, px1:px2] = np.clip(blended_f, 0, 255).astype(np.uint8)
        writer.write(frame)
        frame_idx += 1
        if frame_idx % 30 == 0 or frame_idx == total_frames:
            pct = int(10 + (frame_idx / total_frames) * 82)
            _progress(pct, f"Processing frames ({frame_idx}/{total_frames})...")

    cap.release()
    writer.release()

    _progress(94, "Adding audio...")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", tmp_video, "-i", video_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0?", "-shortest", output_path,
    ]
    r = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"[error] FFmpeg failed: {r.stderr}")
    os.remove(tmp_video)
    os.rmdir(tmp_dir)
    _progress(100, "Done! Video ready.")
    print(f"\n[done] Output: {output_path}")


# Alias for backwards compatibility
def render_poster_video(*args, **kwargs):
    return apply_logo_poster(*args, **kwargs)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Replace a static object in video with a product image.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 object_replace.py \\
      --video video.mp4 \\
      --replacement heineken.png \\
      --target-class cup

  # Expand detection box by 10px on each side:
  python3 object_replace.py \\
      --video video.mp4 \\
      --replacement heineken.png \\
      --target-class cup --pad 10

  # Skip SAM (faster, less precise):
  python3 object_replace.py \\
      --video video.mp4 \\
      --replacement heineken.png \\
      --target-class cup --no-sam
        """,
    )

    parser.add_argument("--video", required=True, help="Input video file")
    parser.add_argument("--replacement", required=True,
                        help="Replacement product image (PNG with transparency preferred)")
    parser.add_argument("--output", default="output.mp4", help="Output video")
    parser.add_argument("--target-class", default="bottle",
                        help="COCO class to detect (default: bottle)")
    parser.add_argument("--pad", type=int, default=0,
                        help="Expand bbox by N pixels on each side (default: 0)")
    parser.add_argument("--no-sam", action="store_true",
                        help="Skip SAM mask refinement")
    parser.add_argument("--no-tracking", action="store_true",
                        help="Disable CSRT motion tracking (static patch)")
    parser.add_argument("--no-depth", action="store_true",
                        help="Disable MiDaS depth for scale")
    parser.add_argument("--no-homography", action="store_true",
                        help="Disable homography perspective warp")
    parser.add_argument("--no-lama", action="store_true",
                        help="Disable LaMa AI inpainting (use OpenCV fallback)")

    args = parser.parse_args()

    render_video(
        video_path=args.video,
        replacement_path=args.replacement,
        output_path=args.output,
        target_class=args.target_class,
        use_sam=not args.no_sam,
        padding=args.pad,
        use_tracking=not args.no_tracking,
        use_depth=not args.no_depth,
        use_homography=not args.no_homography,
        use_lama=not args.no_lama,
    )
