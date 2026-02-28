"""
Lambda 3: chameleon-video-edit

Triggered by EventBridge OfferAccepted event.
Downloads the creator's video from S3, overlays a sponsor banner using
OpenCV (no external API, no torch), uploads the edited video back to S3,
and updates the DynamoDB offer record.

Event shape:
{
  "source": "chameleon.offers",
  "detail-type": "OfferAccepted",
  "detail": {
    "offerId": "...",
    "videoId": "...",
    "companyId": "...",
    "creatorId": "..."
  }
}

Env vars:
  S3_BUCKET_NAME        (default: chameleon-videos-730335328499)
  SPONSOR_LABEL         (default: "Sponsored")  -- text shown in banner
  BANNER_POSITION       (default: "bottom")      -- "top" or "bottom"
"""

import json
import os
import re
import subprocess
import tempfile
from urllib.parse import unquote, urlparse

import boto3
import cv2
import numpy as np

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "chameleon-videos-730335328499")
SPONSOR_LABEL = os.environ.get("SPONSOR_LABEL", "Sponsored")
BANNER_POSITION = os.environ.get("BANNER_POSITION", "bottom")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
s3_client = boto3.client("s3", region_name=AWS_REGION)

videos_table = dynamodb.Table("videos")
offers_table = dynamodb.Table("offers")


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def _set_edit_status(offer_id: str, edit_status: str, edited_location: str = None) -> None:
    update_expr = "SET editStatus = :es"
    expr_vals = {":es": edit_status}
    if edited_location:
        update_expr += ", editedVideoLocation = :el"
        expr_vals[":el"] = edited_location
    offers_table.update_item(
        Key={"offerId": offer_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_vals,
    )


def _s3_key_from_location(s3_location: str) -> str:
    """Convert s3:// or https:// URL to S3 key string."""
    parsed = urlparse(s3_location)
    if parsed.scheme == "s3":
        return unquote(parsed.path.lstrip("/"))
    # https://bucket.s3.amazonaws.com/key
    path = unquote(parsed.path.lstrip("/"))
    bucket_prefix = S3_BUCKET + "/"
    if path.startswith(bucket_prefix):
        path = path[len(bucket_prefix):]
    return path


# ---------------------------------------------------------------------------
# Video editing — sponsor banner overlay via OpenCV
# ---------------------------------------------------------------------------

def _draw_sponsor_banner(frame: np.ndarray, label: str, position: str) -> np.ndarray:
    """
    Draw a semi-transparent sponsor banner across the top or bottom of a frame.
    """
    h, w = frame.shape[:2]
    banner_h = max(40, int(h * 0.08))

    # Semi-transparent dark overlay
    overlay = frame.copy()
    if position == "top":
        y1, y2 = 0, banner_h
    else:
        y1, y2 = h - banner_h, h
    cv2.rectangle(overlay, (0, y1), (w, y2), (0, 0, 0), -1)
    frame = cv2.addWeighted(overlay, 0.55, frame, 0.45, 0)

    # Text
    font = cv2.FONT_HERSHEY_DUPLEX
    font_scale = banner_h / 40.0
    thickness = max(1, int(font_scale * 1.5))
    text = label
    (tw, th), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    tx = (w - tw) // 2
    ty = y1 + (banner_h + th) // 2 - baseline // 2

    # Shadow
    cv2.putText(frame, text, (tx + 2, ty + 2), font, font_scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
    # White text
    cv2.putText(frame, text, (tx, ty), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

    return frame


def _overlay_sponsor_banner(input_path: str, output_path: str, label: str, position: str) -> None:
    """
    Read video frame-by-frame, apply sponsor banner, write output.
    Preserves original FPS and resolution.
    """
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Write to a temp file first, then mux with original audio via ffmpeg
    tmp_noaudio = output_path.replace(".mp4", "_noaudio.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(tmp_noaudio, fourcc, fps, (w, h))

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = _draw_sponsor_banner(frame, label, position)
        writer.write(frame)
        frame_count += 1

    cap.release()
    writer.release()

    if frame_count == 0:
        raise RuntimeError("No frames read from video")

    # Mux with original audio using ffmpeg
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", tmp_noaudio,
            "-i", input_path,
            "-map", "0:v:0",
            "-map", "1:a:0?",   # copy audio track if present (? = optional)
            "-c:v", "libx264",
            "-c:a", "aac",
            "-shortest",
            output_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Fall back to no-audio output if mux fails
        print(f"[warn] ffmpeg mux failed, using no-audio output: {result.stderr[-500:]}")
        import shutil
        shutil.move(tmp_noaudio, output_path)
    else:
        try:
            os.remove(tmp_noaudio)
        except Exception:
            pass

    print(f"[info] Banner applied to {frame_count} frames → {output_path}")


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def handler(event, context):
    print(f"[video_edit_lambda] event: {json.dumps(event)}")

    detail = event.get("detail", {})
    offer_id = detail.get("offerId")
    video_id = detail.get("videoId")
    creator_id = detail.get("creatorId")

    if not all([offer_id, video_id, creator_id]):
        print("[error] Missing required fields in event detail")
        return {"statusCode": 400, "body": "Missing required fields"}

    try:
        _set_edit_status(offer_id, "editing")
    except Exception as e:
        print(f"[warn] Could not set editStatus=editing: {e}")

    # Fetch video record from DynamoDB
    try:
        resp = videos_table.get_item(Key={"videoId": video_id})
        video = resp.get("Item")
        if not video:
            raise ValueError(f"Video {video_id} not found")
    except Exception as e:
        print(f"[error] DynamoDB fetch failed: {e}")
        _set_edit_status(offer_id, "error")
        return {"statusCode": 500, "body": str(e)}

    s3_location = video.get("s3Location")
    if not s3_location:
        print(f"[error] No s3Location on video {video_id}")
        _set_edit_status(offer_id, "error")
        return {"statusCode": 500, "body": "Missing s3Location"}

    s3_key = _s3_key_from_location(s3_location)
    ext_match = re.search(r"\.(\w+)$", s3_key)
    ext = ext_match.group(1) if ext_match else "mp4"

    local_input = f"/tmp/{video_id}.{ext}"
    local_output = f"/tmp/{video_id}_edited.mp4"

    # Download original video
    print(f"[info] Downloading s3://{S3_BUCKET}/{s3_key} → {local_input}")
    try:
        s3_client.download_file(S3_BUCKET, s3_key, local_input)
    except Exception as e:
        print(f"[error] S3 download failed: {e}")
        _set_edit_status(offer_id, "error")
        return {"statusCode": 500, "body": str(e)}

    # Apply sponsor banner
    sponsor_label = SPONSOR_LABEL
    # Try to fetch company name from DynamoDB for a nicer label
    company_id = detail.get("companyId")
    if company_id:
        try:
            companies_table = dynamodb.Table("companies")
            co_resp = companies_table.get_item(Key={"companyId": company_id})
            co = co_resp.get("Item", {})
            name = co.get("name") or co.get("companyName")
            if name:
                sponsor_label = f"Sponsored by {name}"
        except Exception:
            pass  # fall back to default label

    print(f"[info] Applying sponsor banner: '{sponsor_label}'")
    try:
        _overlay_sponsor_banner(local_input, local_output, sponsor_label, BANNER_POSITION)
    except Exception as e:
        print(f"[error] Video edit failed: {e}")
        _set_edit_status(offer_id, "error")
        _cleanup(local_input, local_output)
        return {"statusCode": 500, "body": str(e)}

    # Upload edited video to S3
    output_s3_key = f"videos/{creator_id}/{video_id}_edited.mp4"
    edited_s3_url = f"s3://{S3_BUCKET}/{output_s3_key}"
    print(f"[info] Uploading → {edited_s3_url}")
    try:
        s3_client.upload_file(
            local_output,
            S3_BUCKET,
            output_s3_key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
    except Exception as e:
        print(f"[error] S3 upload failed: {e}")
        _set_edit_status(offer_id, "error")
        _cleanup(local_input, local_output)
        return {"statusCode": 500, "body": str(e)}

    # Update DynamoDB
    try:
        _set_edit_status(offer_id, "complete", edited_s3_url)
        print(f"[info] offer {offer_id}: editStatus=complete, editedVideoLocation={edited_s3_url}")
    except Exception as e:
        print(f"[warn] Final DynamoDB update failed: {e}")

    _cleanup(local_input, local_output)
    print("[info] Pipeline complete.")
    return {"statusCode": 200, "body": f"Edited video at {edited_s3_url}"}


def _cleanup(*paths: str) -> None:
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
