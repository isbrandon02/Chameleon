"""Main video processing pipeline: detect, track, composite, reassemble."""

import os
import subprocess
import tempfile
import cv2
from pathlib import Path

from .detector import load_model, detect_objects, get_most_prominent_detection
from .tracker import init_tracker, update_tracker, bbox_xyxy_to_xywh
from .compositor import composite_frame

_composite_frame_diffusion = None


def _get_composite_frame_diffusion():
    global _composite_frame_diffusion
    if _composite_frame_diffusion is None:
        try:
            from .compositor_diffusion import composite_frame_diffusion
            _composite_frame_diffusion = composite_frame_diffusion
        except ImportError:
            pass
    return _composite_frame_diffusion


def process_video(
    video_path: str,
    replacement_path: str,
    output_path: str,
    clip_duration: float = 5.0,
    start_time: float = 0.0,
    object_type: str = "bottle",
    use_diffusion: bool = False,
) -> str:
    """
    Full pipeline:
    1. Extract frames from video segment
    2. Detect object in first frame
    3. Track object across frames
    4. Composite replacement image
    5. Stitch back with FFmpeg
    
    Returns path to output video.
    """
    video_path = str(Path(video_path).resolve())
    replacement_path = str(Path(replacement_path).resolve())
    output_path = str(Path(output_path).resolve())

    if use_diffusion and _get_composite_frame_diffusion() is None:
        raise ValueError(
            "AI (Diffusion) mode requires: pip install torch diffusers transformers accelerate safetensors. "
            "Use Fast (OpenCV) mode instead, or install the above dependencies."
        )

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    start_frame = int(start_time * fps)
    num_frames = int(clip_duration * fps)
    end_frame = min(start_frame + num_frames, total_frames)
    
    # Load replacement image
    replacement = cv2.imread(replacement_path, cv2.IMREAD_UNCHANGED)
    if replacement is None:
        raise ValueError(f"Cannot load replacement image: {replacement_path}")
    if replacement.shape[2] == 3:
        replacement = cv2.cvtColor(replacement, cv2.COLOR_BGR2BGRA)
    
    # Load YOLOv8 and detect in first frame of segment
    model = load_model()
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    ret, first_frame = cap.read()
    if not ret:
        raise ValueError("Cannot read first frame of segment")
    
    detections = detect_objects(first_frame, model)
    det = get_most_prominent_detection(detections, first_frame.shape)
    if det is None:
        raise ValueError("No bottle/can-like object detected in video segment")
    
    bbox_xyxy = det["bbox"]
    bbox_xywh = bbox_xyxy_to_xywh(bbox_xyxy)
    tracker = init_tracker(bbox_xywh, first_frame)
    
    # Process frames
    tmpdir = tempfile.mkdtemp()
    frames_dir = os.path.join(tmpdir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frame_idx = start_frame
    
    # Process frames before segment: copy as-is
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    for i in range(start_frame):
        ret, frame = cap.read()
        if not ret:
            break
        out_f = os.path.join(frames_dir, f"frame_{i:06d}.png")
        cv2.imwrite(out_f, frame)
    
    # Process segment
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    for i in range(num_frames):
        ret, frame = cap.read()
        if not ret:
            break
        success, bbox = update_tracker(tracker, frame)
        if success:
            x, y, bw, bh = bbox
            x1, y1, x2, y2 = int(x), int(y), int(x + bw), int(y + bh)
            composite_diffusion = _get_composite_frame_diffusion()
            if use_diffusion and composite_diffusion is not None:
                try:
                    frame = composite_diffusion(
                        frame, replacement_path, (x1, y1, x2, y2)
                    )
                except Exception:
                    frame = composite_frame(
                        frame, replacement.copy(), (x1, y1, x2, y2)
                    )
            else:
                frame = composite_frame(frame, replacement.copy(), (x1, y1, x2, y2))
        out_f = os.path.join(frames_dir, f"frame_{frame_idx:06d}.png")
        cv2.imwrite(out_f, frame)
        frame_idx += 1
    
    # Process remaining frames after segment
    while frame_idx < total_frames:
        ret, frame = cap.read()
        if not ret:
            break
        out_f = os.path.join(frames_dir, f"frame_{frame_idx:06d}.png")
        cv2.imwrite(out_f, frame)
        frame_idx += 1
    
    cap.release()
    
    # FFmpeg: stitch frames into video
    frame_pattern = os.path.join(frames_dir, "frame_%06d.png")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", frame_pattern,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    
    # Cleanup
    for f in os.listdir(frames_dir):
        os.remove(os.path.join(frames_dir, f))
    os.rmdir(frames_dir)
    os.rmdir(tmpdir)
    
    return output_path
