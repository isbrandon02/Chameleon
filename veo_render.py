#!/usr/bin/env python3
"""
Google Veo (Vertex AI) video object replacement.

Uses Vertex AI Veo 2.0 for inpainting/object insertion:
  - video + mask + reference image + prompt → edited video

Requires:
  - GOOGLE_CLOUD_PROJECT
  - GOOGLE_APPLICATION_CREDENTIALS (path to service account JSON)
  - GCS_BUCKET (for video/mask/image upload)
  - VERTEX_AI_LOCATION (e.g. us-central1)
"""

from __future__ import annotations

import base64
import os
import tempfile
import time
from typing import Callable

import cv2
import numpy as np


def _progress(pct: float, msg: str) -> None:
    """Default progress callback."""
    print(f"[info] {msg}")


def _get_mask_from_video(
    video_path: str,
    target_class: str,
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    """
    Extract first frame, detect object, refine mask.
    Returns (first_frame_bgr, mask_uint8, bbox) or None.
    """
    from object_replace import detect_object, refine_mask

    cb = progress_callback or _progress
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        cb(0, "Could not read video")
        return None

    cb(5, "Detecting object...")
    bbox = detect_object(frame, target_class=target_class)
    if not bbox:
        cb(0, "No object detected")
        return None

    cb(15, "Refining mask (SAM)...")
    mask = refine_mask(frame, bbox)
    return frame, mask, bbox


def _upload_to_gcs(
    local_path: str,
    gcs_uri: str,
) -> str:
    """Upload file to GCS. Returns gcs_uri."""
    from google.cloud import storage

    # gcs_uri: gs://bucket/path/to/object
    parts = gcs_uri.replace("gs://", "").split("/", 1)
    bucket_name = parts[0]
    blob_path = parts[1]

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_filename(local_path, content_type=_mime_for_path(local_path))
    return gcs_uri


def _get_video_meta(video_path: str) -> tuple[float, str]:
    """Return (duration_sec, aspect_ratio "9:16" or "16:9")."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    duration = frame_count / fps if fps > 0 else 8.0
    aspect = "9:16" if h >= w and w > 0 else "16:9"
    return duration, aspect


def _mime_for_path(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in ("mp4", "mov"):
        return "video/mp4"
    if ext in ("png",):
        return "image/png"
    if ext in ("jpg", "jpeg"):
        return "image/jpeg"
    return "application/octet-stream"


def _call_veo_predict_long_running(
    project: str,
    location: str,
    model_id: str,
    instances: list[dict],
    parameters: dict,
) -> str:
    """
    Call Vertex AI predictLongRunning. Returns operation name.
    """
    import google.auth
    import google.auth.transport.requests
    import requests

    creds, _ = google.auth.default()
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    parent = f"projects/{project}/locations/{location}/publishers/google/models/{model_id}"
    url = f"https://{location}-aiplatform.googleapis.com/v1/{parent}:predictLongRunning"
    headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
    body = {"instances": instances, "parameters": parameters}
    resp = requests.post(url, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["name"]  # operation name


def _poll_operation_and_get_output(
    operation_name: str,
    storage_uri_prefix: str,
    output_path: str,
    project: str,
    location: str,
    model_id: str,
    progress_callback: Callable[[float, str], None] | None = None,
) -> None:
    """
    Poll long-running operation via fetchPredictOperation until done, then download from GCS.
    Veo requires fetchPredictOperation for polling (direct GET returns 404).
    """
    import google.auth
    import google.auth.transport.requests
    import requests
    from google.cloud import storage

    cb = progress_callback or _progress
    creds, _ = google.auth.default()
    auth_req = google.auth.transport.requests.Request()

    fetch_url = (
        f"https://{location}-aiplatform.googleapis.com/v1/"
        f"projects/{project}/locations/{location}/publishers/google/models/{model_id}"
        ":fetchPredictOperation"
    )
    headers = {"Content-Type": "application/json"}
    body = {"operationName": operation_name}

    while True:
        creds.refresh(auth_req)
        headers["Authorization"] = f"Bearer {creds.token}"
        resp = requests.post(fetch_url, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        op = resp.json()
        done = op.get("done", False)
        if done:
            if "error" in op:
                raise RuntimeError(op["error"].get("message", "Operation failed"))
            break
        cb(50, "Veo processing (2–15 min typical)...")
        time.sleep(30)

    # Veo writes to storageUri; list prefix and download first video
    parts = storage_uri_prefix.replace("gs://", "").split("/", 1)
    bucket_name, prefix = parts[0], parts[1].rstrip("/")
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix))
    video_blobs = [b for b in blobs if b.name.endswith(".mp4")]
    if not video_blobs:
        raise RuntimeError("No output video in GCS; check storageUri prefix")
    video_blobs[0].download_to_filename(output_path)


def render_video_veo(
    video_path: str,
    replacement_path: str,
    output_path: str,
    target_class: str = "bottle",
    progress_callback: Callable[[float, str], None] | None = None,
) -> None:
    """
    Replace object in video using Google Veo (Vertex AI).
    Uses video + mask + reference image + prompt → edited video.
    """
    cb = progress_callback or _progress
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    bucket_name = os.environ.get("GCS_BUCKET")
    location = os.environ.get("VERTEX_AI_LOCATION", "us-central1")

    if not project or not bucket_name:
        raise RuntimeError(
            "Set GOOGLE_CLOUD_PROJECT and GCS_BUCKET for Veo. "
            "See .env.example for setup."
        )

    # 1. Get mask from first frame
    result = _get_mask_from_video(video_path, target_class, cb)
    if not result:
        raise RuntimeError("Could not detect object or generate mask")
    first_frame, mask, bbox = result

    # 2. Save mask as PNG
    mask_path = tempfile.mktemp(suffix=".png")
    cv2.imwrite(mask_path, mask)

    # 3. Upload to GCS
    job_id = os.urandom(8).hex()
    video_gcs = f"gs://{bucket_name}/veo/{job_id}/input.mp4"
    mask_gcs = f"gs://{bucket_name}/veo/{job_id}/mask.png"
    cb(20, "Uploading to GCS...")
    _upload_to_gcs(video_path, video_gcs)
    _upload_to_gcs(mask_path, mask_gcs)
    os.remove(mask_path)

    # 4. Call Veo predictLongRunning
    # Veo 2.0 insert-object: video + mask + prompt only. "Image and video cannot both be set."
    # Describe the product in the prompt; reference image not supported for this mode.
    model_id = "veo-2.0-generate-preview"
    storage_uri = f"gs://{bucket_name}/veo/{job_id}/output"
    max_dur = int(os.environ.get("VEO_MAX_DURATION_SEC", "8"))
    duration, aspect = _get_video_meta(video_path)
    duration_sec = min(int(round(duration)), max_dur)
    duration_sec = max(5, min(8, duration_sec))  # Veo supports 5–8 sec
    product_desc = target_class.replace("_", " ")
    instances = [
        {
            "prompt": f"Replace masked object with a realistic {product_desc}. Preserve lighting and perspective.",
            "video": {"gcsUri": video_gcs, "mimeType": "video/mp4"},
            "mask": {
                "gcsUri": mask_gcs,
                "mimeType": "image/png",
                "maskMode": "insert",
            },
        }
    ]
    params = {
        "durationSeconds": duration_sec,
        "aspectRatio": aspect,
        "storageUri": storage_uri,
        "sampleCount": 1,
    }
    op_name = _call_veo_predict_long_running(
        project=project, location=location, model_id=model_id,
        instances=instances, parameters=params,
    )

    # 5. Poll and download
    storage_prefix = f"gs://{bucket_name}/veo/{job_id}/output"
    _poll_operation_and_get_output(
        op_name, storage_prefix, output_path, project, location, model_id, cb
    )
    cb(100, "Done! Video ready.")
    print(f"\n[done] Output: {output_path}")


def is_veo_available() -> bool:
    """True if GCP creds and bucket are configured for Veo."""
    return bool(
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        and os.environ.get("GCS_BUCKET")
    )
