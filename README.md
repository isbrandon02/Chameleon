# 🦎 Chameleon — AI-Powered Object Replacement for Video

Replace a selected object (bottle, can, cup) in a short video clip with your own image while preserving lighting, shadows, perspective, and camera movement.

**Stack:** YOLOv8 (detection) + OpenCV (tracking) + [Fast: OpenCV | AI: SD + ControlNet + IP-Adapter] + FFmpeg

---

## Modes

- **Fast (OpenCV)** — Color transfer + seamless clone. No extra deps, runs on CPU.
- **AI (SD + ControlNet)** — Stable Diffusion + ControlNet Inpainting + IP-Adapter for realistic object replacement. Best free approach. Requires GPU (8GB+ VRAM).

---

## Quick Start

```bash
# 1. Create virtual env
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) For AI mode — install diffusion stack (requires GPU)
pip install torch diffusers transformers accelerate safetensors

# 4. Install FFmpeg (required)
# macOS: brew install ffmpeg
# Ubuntu: sudo apt install ffmpeg

# 5. Run Streamlit dashboard
streamlit run app.py
```

---

## Pipeline Overview

1. **Bounding box detection** — YOLOv8 detects bottle/can-like objects in the first frame
2. **Frame tracking** — OpenCV CSRT tracker follows the object across frames
3. **Compositing** — Fast: color transfer + seamless clone. AI: SD + ControlNet Inpainting + IP-Adapter for photorealistic blending
4. **Stitching** — FFmpeg reassembles frames into MP4

---

## Usage

- **Video input:** MP4, AVI, MOV
- **Replacement image:** PNG (transparent) or JPG
- **Clip duration:** 3–10 seconds (default 5)
- **Start time:** Auto (0s) or manual override

---

## Project Structure

```
Chameleon/
├── app.py              # Streamlit dashboard
├── pipeline/
│   ├── detector.py     # YOLOv8 object detection
│   ├── tracker.py      # OpenCV tracking
│   ├── compositor.py          # OpenCV: color transfer + seamless clone
│   ├── compositor_diffusion.py # AI: SD + ControlNet + IP-Adapter
│   └── video_processor.py  # Full pipeline
├── frontend/           # (optional) React frontend
└── requirements.txt
```

---

## License

Open source — hackathon-ready. 🚀
