"""
Diffusion compositing: SD + ControlNet Inpainting + IP-Adapter.
Best free approach: structure-aware inpainting + reference image.
Requires GPU (CUDA/MPS) for reasonable speed.
"""

import cv2
import numpy as np
import torch
from PIL import Image

_pipeline = None


def _get_device():
    """Detect best available device."""
    try:
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _make_inpaint_condition(image, image_mask):
    """Create control image for ControlNet inpainting. Masked pixels set to -1."""
    image = np.array(image.convert("RGB")).astype(np.float32) / 255.0
    image_mask = np.array(image_mask.convert("L")).astype(np.float32) / 255.0
    assert image.shape[:2] == image_mask.shape[:2]
    image[image_mask > 0.5] = -1.0
    image = np.expand_dims(image, 0).transpose(0, 3, 1, 2)
    return torch.from_numpy(image)


def _load_pipeline(device="cuda"):
    """Lazy-load SD + ControlNet Inpainting + IP-Adapter pipeline."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    from diffusers import (
        StableDiffusionControlNetInpaintPipeline,
        ControlNetModel,
        DDIMScheduler,
    )

    dtype = torch.float16 if device != "cpu" else torch.float32

    controlnet = ControlNetModel.from_pretrained(
        "lllyasviel/control_v11p_sd15_inpaint",
        torch_dtype=dtype,
    )
    _pipeline = StableDiffusionControlNetInpaintPipeline.from_pretrained(
        "runwayml/stable-diffusion-v1-5",
        controlnet=controlnet,
        torch_dtype=dtype,
    )
    _pipeline.scheduler = DDIMScheduler.from_config(_pipeline.scheduler.config)

    _pipeline = _pipeline.to(device)

    # IP-Adapter for reference image (user's bottle/can)
    try:
        _pipeline.load_ip_adapter(
            "h94/IP-Adapter",
            subfolder="models",
            weight_name="ip-adapter-plus_sd15.safetensors",
        )
        _pipeline.set_ip_adapter_scale(0.8)
        _has_ip_adapter = True
    except Exception:
        _has_ip_adapter = False
    if device == "cuda":
        _pipeline.enable_attention_slicing()
    setattr(_pipeline, "_has_ip_adapter", _has_ip_adapter)
    return _pipeline


def _bbox_to_xyxy(bbox):
    x1, y1, a, b = bbox[:4]
    if a > x1 and b > y1:
        return x1, y1, int(a), int(b)
    return x1, y1, int(x1 + a), int(y1 + b)


def composite_frame_diffusion(
    frame,
    replacement_path,
    bbox,
    prompt="a bottle, product photography, photorealistic, high quality, 8k",
    negative_prompt="blurry, low quality, distorted, ugly, bad anatomy, deformed",
    strength=0.99,
    steps=20,
    guidance_scale=7.5,
):
    """
    Replace object using SD + ControlNet Inpainting + IP-Adapter.
    Crops around bbox, inpaints with reference, pastes back.
    Returns composited frame (BGR).
    """
    device = _get_device()
    if device == "cpu":
        raise RuntimeError(
            "AI (Diffusion) mode requires a GPU (CUDA or Apple MPS). "
            "Use Fast (OpenCV) mode on CPU."
        )

    pipeline = _load_pipeline(device)
    h_frame, w_frame = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in _bbox_to_xyxy(bbox)]
    w, h = x2 - x1, y2 - y1
    if w < 8 or h < 8:
        return frame

    # Crop with padding
    pad = max(32, int(0.4 * max(w, h)))
    cx1 = max(0, x1 - pad)
    cy1 = max(0, y1 - pad)
    cx2 = min(w_frame, x2 + pad)
    cy2 = min(h_frame, y2 + pad)
    crop = frame[cy1:cy2, cx1:cx2]
    crop_h, crop_w = crop.shape[:2]

    # Resize to 512 for SD 1.5
    sd_size = 512
    scale = min(sd_size / crop_w, sd_size / crop_h)
    new_w = int(crop_w * scale)
    new_h = int(crop_h * scale)
    crop_resized = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    if len(crop_resized.shape) == 2:
        crop_resized = cv2.cvtColor(crop_resized, cv2.COLOR_GRAY2RGB)
    else:
        crop_resized = cv2.cvtColor(crop_resized, cv2.COLOR_BGR2RGB)

    # Mask: white = inpaint
    mask_crop = np.zeros((crop_h, crop_w), dtype=np.uint8)
    mx1, my1 = x1 - cx1, y1 - cy1
    mx2, my2 = x2 - cx1, y2 - cy1
    mask_crop[my1:my2, mx1:mx2] = 255
    mask_resized = cv2.resize(mask_crop, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
    mask_resized = cv2.GaussianBlur(mask_resized, (5, 5), 1)
    mask_resized = (mask_resized > 127).astype(np.uint8) * 255

    # Pad to 512x512
    pad_r, pad_b = sd_size - new_w, sd_size - new_h
    if pad_r > 0 or pad_b > 0:
        crop_resized = np.pad(
            crop_resized,
            ((0, max(0, pad_b)), (0, max(0, pad_r)), (0, 0)),
            mode="edge",
        )[:sd_size, :sd_size]
        mask_resized = np.pad(
            mask_resized,
            ((0, max(0, pad_b)), (0, max(0, pad_r))),
            mode="constant",
            constant_values=0,
        )[:sd_size, :sd_size]

    image_pil = Image.fromarray(crop_resized)
    mask_pil = Image.fromarray(mask_resized)
    control_image = _make_inpaint_condition(image_pil, mask_pil).to(
        pipeline.device, dtype=pipeline.controlnet.dtype
    )

    # Reference image for IP-Adapter
    ref_img = Image.open(replacement_path).convert("RGB").resize(
        (512, 512), Image.Resampling.LANCZOS
    )

    kwargs = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "image": image_pil,
        "mask_image": mask_pil,
        "control_image": control_image,
        "strength": strength,
        "num_inference_steps": steps,
        "guidance_scale": guidance_scale,
        "eta": 1.0,
    }
    if getattr(pipeline, "_has_ip_adapter", False):
        kwargs["ip_adapter_image"] = ref_img

    with torch.inference_mode():
        result = pipeline(**kwargs).images[0]

    result_np = np.array(result)[:new_h, :new_w]
    result_bgr = cv2.cvtColor(result_np, cv2.COLOR_RGB2BGR)
    result_full = cv2.resize(result_bgr, (crop_w, crop_h), interpolation=cv2.INTER_LINEAR)

    # Blend back
    mask_soft = cv2.GaussianBlur(mask_crop.astype(np.float32) / 255.0, (21, 21), 5)
    mask_soft = np.expand_dims(mask_soft, axis=2)
    frame_out = frame.copy()
    roi = frame_out[cy1:cy2, cx1:cx2]
    blended = (mask_soft * result_full + (1 - mask_soft) * roi).astype(np.uint8)
    frame_out[cy1:cy2, cx1:cx2] = blended

    return frame_out
