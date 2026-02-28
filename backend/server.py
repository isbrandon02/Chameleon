#!/usr/bin/env python3
"""
Simple web server for video object replacement.
Upload a video and replacement image, get back a VIDEO (product swapped, rest unchanged).

Uses Google Veo (Vertex AI) when USE_VEO=true and GCP is configured.
"""

import os

# Load .env for Veo config
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import tempfile
import threading
import uuid

from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename

# Import the video pipeline
from object_replace import render_video, render_poster_video, apply_logo_poster

# Google Veo (Vertex AI) — use when GCP configured
try:
    from veo_render import render_video_veo, is_veo_available
except ImportError:
    render_video_veo = None
    is_veo_available = lambda: False

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB max
ALLOWED_VIDEO = {"mp4", "mov", "avi", "webm", "mkv"}
ALLOWED_IMAGE = {"png", "jpg", "jpeg", "webp"}

# In-memory job storage: job_id -> {progress, status, output_path, error, work_dir}
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def allowed_file(filename, extensions):
    return filename and "." in filename and filename.rsplit(".", 1)[1].lower() in extensions


def run_job(
    job_id: str,
    video_path: str,
    output_path: str,
    work_dir: str,
    product_path: str | None,
    logo_path: str | None,
    target_class: str,
    poster_region: tuple[float, float, float, float],
    fast_mode: bool = False,
):
    def on_progress(pct: int, msg: str):
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["progress"] = pct
                jobs[job_id]["message"] = msg

    try:
        current_video = video_path
        if product_path:
            product_output = os.path.join(work_dir, "product_output.mp4")
            use_veo = (
                os.environ.get("USE_VEO", "true").lower() in ("true", "1", "yes")
                and render_video_veo is not None
                and is_veo_available()
            )
            if use_veo:
                render_video_veo(
                    video_path=current_video,
                    replacement_path=product_path,
                    output_path=product_output,
                    target_class=target_class,
                    progress_callback=lambda p, m: on_progress(int(p * 0.9) if logo_path else p, m),
                )
            else:
                render_video(
                    video_path=current_video,
                    replacement_path=product_path,
                    output_path=product_output,
                    target_class=target_class,
                    use_sam=not fast_mode,
                    use_depth=not fast_mode,
                    use_lama=not fast_mode,
                    use_tracking=not fast_mode,
                    use_homography=not fast_mode,
                    progress_callback=lambda p, m: on_progress(int(p * 0.9) if logo_path else p, m),
                )
            current_video = product_output

        if logo_path:
            apply_logo_poster(
                video_path=current_video,
                logo_path=logo_path,
                output_path=output_path,
                poster_region=poster_region,
                auto_region=(poster_region is None),
                progress_callback=lambda p, m: on_progress(90 + int(p * 0.1), m) if product_path else on_progress(p, m),
            )
        elif product_path:
            os.replace(current_video, output_path)
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["status"] = "done"
                jobs[job_id]["progress"] = 100
                jobs[job_id]["message"] = "Video ready"
    except BaseException as e:
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["status"] = "error"
                err_msg = str(e)
                # sys.exit(1) yields SystemExit(1) -> str(e) == "1"
                if err_msg in ("0", "1", "2"):
                    err_msg = "Processing failed. Check server logs for details."
                jobs[job_id]["error"] = err_msg
    finally:
        try:
            for p in (video_path, product_path, logo_path):
                if p and os.path.isfile(p):
                    os.unlink(p)
        except OSError:
            pass


@app.route("/")
def index():
    return send_file(os.path.join(os.path.dirname(__file__), "templates", "index.html"))


def _float_form(form_val, default: float) -> float:
    try:
        v = request.form.get(form_val, default)
        return float(v) if v != "" else default
    except (ValueError, TypeError):
        return default


@app.route("/api/process", methods=["POST"])
def process():
    video = request.files.get("video")
    product_image = request.files.get("product")
    logo_image = request.files.get("logo")
    target_class = (request.form.get("target_class") or "bottle").strip()
    poster_auto = (request.form.get("poster_auto") or "true").strip().lower() in ("true", "1", "yes")
    poster_x = _float_form("poster_x", 30)
    poster_y = _float_form("poster_y", 15)
    poster_w = _float_form("poster_w", 40)
    poster_h = _float_form("poster_h", 30)
    poster_region = None if poster_auto else (poster_x, poster_y, poster_w, poster_h)
    fast_mode = (request.form.get("fast") or "false").strip().lower() in ("true", "1", "yes")

    if not video:
        return jsonify({"error": "Missing video file"}), 400
    if not product_image and not logo_image:
        return jsonify({"error": "Provide at least one: product image or logo image"}), 400

    if not allowed_file(video.filename, ALLOWED_VIDEO):
        return jsonify({"error": f"Video must be one of: {', '.join(ALLOWED_VIDEO)}"}), 400
    if product_image and not allowed_file(product_image.filename, ALLOWED_IMAGE):
        return jsonify({"error": f"Product image must be PNG, JPG, or WebP"}), 400
    if logo_image and not allowed_file(logo_image.filename, ALLOWED_IMAGE):
        return jsonify({"error": f"Logo image must be PNG, JPG, or WebP"}), 400

    job_id = str(uuid.uuid4())[:12]
    work_dir = tempfile.mkdtemp()
    video_path = os.path.join(work_dir, secure_filename(video.filename))
    product_path = None
    logo_path = None
    if product_image:
        product_path = os.path.join(work_dir, "product_" + secure_filename(product_image.filename))
        product_image.save(product_path)
    if logo_image:
        logo_path = os.path.join(work_dir, "logo_" + secure_filename(logo_image.filename))
        logo_image.save(logo_path)
    output_path = os.path.join(work_dir, f"output_{job_id}.mp4")

    video.save(video_path)

    with jobs_lock:
        jobs[job_id] = {
            "progress": 0,
            "message": "Starting...",
            "status": "processing",
            "error": None,
            "output_path": output_path,
            "work_dir": work_dir,
        }

    thread = threading.Thread(
        target=run_job,
        args=(job_id, video_path, output_path, work_dir, product_path, logo_path, target_class, poster_region, fast_mode),
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "progress": job["progress"],
        "message": job.get("message", ""),
        "status": job["status"],
        "error": job.get("error"),
    })


@app.route("/api/result/<job_id>")
def result(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] == "processing":
        return jsonify({"error": "Still processing"}), 202
    if job["status"] == "error":
        return jsonify({"error": job.get("error", "Processing failed")}), 500

    output_path = job["output_path"]
    if not output_path or not os.path.isfile(output_path):
        return jsonify({"error": "Output file not found"}), 500

    resp = send_file(
        output_path,
        mimetype="video/mp4",
        as_attachment=True,
        download_name=f"output_{job_id}.mp4",
    )

    # Clean up job and temp dir after a short delay (so response is sent first)
    work_dir = job.get("work_dir")

    def cleanup():
        with jobs_lock:
            if job_id in jobs:
                del jobs[job_id]
        if work_dir and os.path.isdir(work_dir):
            try:
                for f in os.listdir(work_dir):
                    try:
                        os.unlink(os.path.join(work_dir, f))
                    except OSError:
                        pass
                os.rmdir(work_dir)
            except OSError:
                pass

    threading.Timer(5.0, cleanup).start()
    return resp


if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(__file__), "templates"), exist_ok=True)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
