"""OpenCV compositing: perspective transform, seamless clone, color transfer."""

import cv2
import numpy as np


def color_transfer(source, target_region, mask=None):
    """
    Reinhard-style color transfer: match source colors to target region.
    Makes replacement blend with scene lighting. Uses LAB space for better results.
    """
    if source.size == 0 or target_region.size == 0:
        return source
    
    # Convert to LAB (decorrelated color space)
    src = source.astype(np.float32)
    tgt = target_region.astype(np.float32)
    
    src_lab = cv2.cvtColor(np.clip(src, 0, 255).astype(np.uint8), cv2.COLOR_BGR2LAB)
    tgt_lab = cv2.cvtColor(np.clip(tgt, 0, 255).astype(np.uint8), cv2.COLOR_BGR2LAB)
    
    src_lab = src_lab.astype(np.float32)
    tgt_lab = tgt_lab.astype(np.float32)
    
    if mask is not None and mask.any():
        # Use only masked pixels for source stats
        src_pixels = src_lab[mask > 0]
        if len(src_pixels) < 10:
            return source
        src_mean = src_pixels.mean(axis=0)
        src_std = src_pixels.std(axis=0) + 1e-6
    else:
        src_mean = src_lab.reshape(-1, 3).mean(axis=0)
        src_std = src_lab.reshape(-1, 3).std(axis=0) + 1e-6
    
    tgt_mean = tgt_lab.reshape(-1, 3).mean(axis=0)
    tgt_std = tgt_lab.reshape(-1, 3).std(axis=0) + 1e-6
    
    # Transfer: normalize source to target distribution
    result_lab = (src_lab - src_mean) * (tgt_std / src_std) + tgt_mean
    result_lab = np.clip(result_lab, 0, 255).astype(np.uint8)
    result_bgr = cv2.cvtColor(result_lab, cv2.COLOR_LAB2BGR)
    return result_bgr


def warp_replacement(replacement_rgba, bbox, frame_shape):
    """Warp replacement image to fit bbox with perspective."""
    if len(bbox) == 4 and bbox[2] > 0 and bbox[3] > 0 and bbox[2] < 10000:
        x, y, w, h = bbox
    else:
        x1, y1, x2, y2 = bbox
        x, y, w, h = x1, y1, x2 - x1, y2 - y1
    
    if w <= 0 or h <= 0:
        return None, None
    
    rh, rw = replacement_rgba.shape[:2]
    src_pts = np.array([[0, 0], [rw, 0], [rw, rh], [0, rh]], dtype=np.float32)
    dst_pts = np.array([
        [x, y], [x + w, y], [x + w, y + h], [x, y + h]
    ], dtype=np.float32)
    
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    h_frame, w_frame = frame_shape[:2]
    warped = cv2.warpPerspective(replacement_rgba, M, (w_frame, h_frame))
    return warped, (x, y, w, h)


def _get_background_ring(frame, x, y, w, h, pad=8):
    """Sample background around bbox (ring outside object) for color matching."""
    hf, wf = frame.shape[:2]
    # Inner: bbox expanded slightly. Outer: bbox + pad. Ring = outer - inner.
    inner = (max(0, x - pad), max(0, y - pad),
             min(wf, x + w + pad), min(hf, y + h + pad))
    outer = (max(0, x - pad - 20), max(0, y - pad - 20),
             min(wf, x + w + pad + 20), min(hf, y + h + pad + 20))
    # Use expanded region around bbox as background reference
    x1, y1 = max(0, x - 30), max(0, y - 30)
    x2, y2 = min(wf, x + w + 30), min(hf, y + h + 30)
    return frame[y1:y2, x1:x2]


def add_contact_shadow(frame, bbox):
    """Tight, dark shadow at object base (physics: occlusion where object meets surface)."""
    x, y, w, h = [int(v) for v in bbox]
    hf, wf = frame.shape[:2]
    base_y = min(y + h, hf - 1)
    sh_h = max(3, int(h * 0.08))
    y_end = min(base_y + sh_h, hf)
    x_start = max(0, x - int(w * 0.1))
    x_end = min(wf, x + w + int(w * 0.1))
    if base_y >= y_end - 1 or x_start >= x_end - 1:
        return frame
    region = frame[base_y:y_end, x_start:x_end].astype(np.float32)
    grad = np.linspace(0.5, 0, region.shape[0]).reshape(-1, 1)
    region = region * (1 - grad)
    k = max(3, int(min(w, h) * 0.15)) | 1
    frame[base_y:y_end, x_start:x_end] = np.clip(
        cv2.GaussianBlur(region, (k, k), 0), 0, 255
    ).astype(np.uint8)
    return frame


def add_soft_shadow(frame, bbox, intensity=0.35, blur_radius=8):
    """Diffuse cast shadow below object (physics: soft light scattering)."""
    x, y, w, h = [int(v) for v in bbox]
    hf, wf = frame.shape[:2]
    shadow_h = max(4, int(h * 0.25))
    y_start = min(y + h, hf - 1)
    y_end = min(y_start + shadow_h, hf)
    x_start = max(0, x - int(w * 0.2))
    x_end = min(wf, x + w + int(w * 0.2))
    if y_start >= y_end - 1 or x_start >= x_end - 1:
        return frame
    region = frame[y_start:y_end, x_start:x_end].astype(np.float32)
    rows = region.shape[0]
    grad = np.linspace(intensity, 0, rows).reshape(-1, 1)
    region = region * (1 - grad)
    k = max(3, blur_radius | 1)
    frame[y_start:y_end, x_start:x_end] = np.clip(
        cv2.GaussianBlur(region, (k, k), 0), 0, 255
    ).astype(np.uint8)
    return frame


def add_reflection(frame, warped_rgba, bbox):
    """Faint reflection below object (physics: surface reflectivity)."""
    x, y, w, h = [int(v) for v in bbox]
    hf, wf = frame.shape[:2]
    refl_h = max(4, int(h * 0.2))
    y_end = min(y + h + refl_h, hf)
    if y + h >= y_end - 1:
        return frame
    # Crop object region, flip vertically
    obj = warped_rgba[y:y+h, x:x+w]
    if obj.size == 0:
        return frame
    flipped = cv2.flip(obj, 0)
    refl = cv2.resize(flipped, (w, min(refl_h, flipped.shape[0])), interpolation=cv2.INTER_LINEAR)
    if refl.shape[2] == 4:
        alpha = (refl[:, :, 3] / 255.0) * 0.12
        alpha = np.expand_dims(alpha, 2)
    else:
        alpha = np.ones((refl.shape[0], refl.shape[1], 1), dtype=np.float32) * 0.12
    ry1, ry2 = y + h, y + h + refl.shape[0]
    rx1, rx2 = x, x + refl.shape[1]
    if ry2 > hf or rx2 > wf:
        return frame
    roi = frame[ry1:ry2, rx1:rx2].astype(np.float32)
    blend = alpha * refl[:, :, :3] + (1 - alpha) * roi
    frame[ry1:ry2, rx1:rx2] = np.clip(blend, 0, 255).astype(np.uint8)
    return frame


def apply_ambient_occlusion(overlay_bgr, _alpha=None, strength=0.15):
    """Darken bottom/edges of object (physics: less ambient light in crevices)."""
    h, w = overlay_bgr.shape[:2]
    darken = np.ones((h, w), dtype=np.float32)
    # Bottom gradient (contact with surface — darker at base)
    for row in range(h):
        darken[row] *= 1.0 - strength * (row / max(h, 1))
    # Edge falloff
    y_center, x_center = h / 2, w / 2
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    dist = np.sqrt((yy - y_center) ** 2 + (xx - x_center) ** 2)
    max_d = max(np.sqrt(x_center**2 + y_center**2), 1)
    edge = np.clip(dist / max_d, 0, 1)
    darken *= 1.0 - strength * 0.5 * edge
    darken = np.clip(darken, 0, 1)
    overlay_bgr = overlay_bgr.astype(np.float32) * np.expand_dims(darken, 2)
    return np.clip(overlay_bgr, 0, 255).astype(np.uint8)


def composite_frame(frame, replacement_rgba, bbox, add_shadow=True, add_blur=True):
    """
    Realistic compositing: color transfer + OpenCV seamless clone (Poisson blend).
    Meshes the replacement into the video with natural edges and lighting.
    """
    frame_shape = frame.shape
    if len(bbox) == 4:
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[0] + bbox[2], bbox[1] + bbox[3]
    else:
        x1, y1, x2, y2 = bbox
    
    x, y, w, h = x1, y1, x2 - x1, y2 - y1
    hf, wf = frame.shape[:2]
    
    if w < 4 or h < 4:
        return frame
    
    # Ensure replacement has alpha
    if replacement_rgba.shape[2] == 3:
        replacement_rgba = cv2.cvtColor(replacement_rgba, cv2.COLOR_BGR2BGRA)
        replacement_rgba[:, :, 3] = 255
    
    # Soften alpha edges
    if add_blur:
        alpha = replacement_rgba[:, :, 3]
        alpha = cv2.GaussianBlur(alpha, (5, 5), 0)
        replacement_rgba = replacement_rgba.copy()
        replacement_rgba[:, :, 3] = alpha
    
    warped, _ = warp_replacement(replacement_rgba, (x, y, w, h), frame_shape)
    if warped is None:
        return frame

    # Physics: ambient occlusion (darker bottom/edges in object-local coords)
    obj_crop = warped[y:y+h, x:x+w]
    if obj_crop.size > 0 and (obj_crop[:, :, 3] > 25).any():
        obj_bgr = obj_crop[:, :, :3].copy()
        obj_bgr = apply_ambient_occlusion(obj_bgr, None, strength=0.1)
        mask = (obj_crop[:, :, 3] > 25)[:, :, np.newaxis]
        warped[y:y+h, x:x+w, :3] = np.where(mask, obj_bgr, warped[y:y+h, x:x+w, :3])

    result = frame.copy()
    if len(result.shape) == 2:
        result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)
    
    # Crop region with padding for seamless clone
    pad = max(4, min(w, h) // 4)
    rx1 = max(0, x - pad)
    ry1 = max(0, y - pad)
    rx2 = min(wf, x + w + pad)
    ry2 = min(hf, y + h + pad)
    
    src_crop = warped[ry1:ry2, rx1:rx2]
    if src_crop.size == 0:
        return frame
    
    # Build mask from alpha (dilate slightly for smoother blend boundary)
    alpha_crop = src_crop[:, :, 3]
    mask = (alpha_crop > 25).astype(np.uint8) * 255
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    
    if mask.sum() < 100:
        # Fallback to alpha blend if mask is too small
        alpha = warped[:, :, 3:4] / 255.0
        m = (alpha > 0.01).squeeze(axis=2)
        result = result.astype(np.float32)
        result[m] = alpha[m] * warped[m][:, :3] + (1 - alpha[m]) * result[m]
        result = result.astype(np.uint8)
    else:
        # Color transfer: match replacement to scene lighting
        bg_ring = _get_background_ring(result, x, y, w, h, pad)
        src_bgr = src_crop[:, :, :3]
        obj_mask = (alpha_crop > 25).astype(np.uint8)
        src_bgr = color_transfer(src_bgr, bg_ring, mask=obj_mask if obj_mask.any() else None)
        
        # Ensure src and mask are 3-channel / valid for seamlessClone
        center = (int(x + w / 2), int(y + h / 2))
        try:
            result = cv2.seamlessClone(
                src_bgr, result, mask,
                center, cv2.MIXED_CLONE
            )
        except cv2.error:
            # Fallback if seamlessClone fails (e.g. mask/region issue)
            alpha = warped[:, :, 3:4] / 255.0
            m = (alpha > 0.01).squeeze(axis=2)
            result = result.astype(np.float32)
            result[m] = alpha[m] * warped[m][:, :3] + (1 - alpha[m]) * result[m]
            result = result.astype(np.uint8)
    
    # Physics: shadows + reflection
    if add_shadow:
        add_contact_shadow(result, (x, y, w, h))
        add_soft_shadow(result, (x, y, w, h))
    add_reflection(result, warped, (x, y, w, h))

    return result
