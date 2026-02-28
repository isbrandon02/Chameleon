"""
Chameleon — AI-Powered Object Replacement for Video
Streamlit dashboard (hackathon-ready).
"""

import os
import tempfile
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Chameleon", page_icon="🦎", layout="wide")

# Add pipeline to path (import deferred until run to speed up startup)
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    st.title("🦎 Chameleon — Object Replacement for Video")
    st.caption("Replace bottles, cans, cups in video with your image. Uses YOLOv8 + OpenCV + FFmpeg.")

    # Section 1 — Upload Video
    st.header("1. Upload Video")
    video_file = st.file_uploader("Upload MP4 video", type=["mp4", "avi", "mov"], key="video")
    if video_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
            tmp.write(video_file.read())
            video_path = tmp.name
        st.video(video_path)
    else:
        video_path = None
        st.info("Upload an MP4 video file.")

    # Section 2 — Upload Replacement Image
    st.header("2. Upload Replacement Image")
    replace_file = st.file_uploader("Upload replacement image (PNG with transparency recommended)", type=["png", "jpg", "jpeg"], key="replace")
    if replace_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(replace_file.name).suffix) as tmp:
            tmp.write(replace_file.read())
            replace_path = tmp.name
        col1, col2 = st.columns(2)
        with col1:
            st.image(replace_path, caption="Replacement image")
    else:
        replace_path = None
        st.info("Upload a PNG (transparent background) or JPG replacement image.")

    # Section 3 — Replacement Settings
    st.header("3. Replacement Settings")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        object_type = st.selectbox("Object type", ["Bottle", "Can", "Cup", "Custom"], index=0)
    with col2:
        clip_duration = st.slider("Clip duration (seconds)", 3, 10, 5)
    with col3:
        mode = st.radio(
            "Mode",
            ["Fast (OpenCV)", "AI (SD + ControlNet)"],
            help="AI: SD + ControlNet Inpainting + IP-Adapter for realistic replacement (8GB+ VRAM)",
        )
    with col4:
        start_mode = st.radio("Replacement start time", ["Auto-detect (0s)", "Manual override"])
    start_time = 0.0
    if start_mode == "Manual override":
        start_time = st.number_input("Start time (seconds)", 0.0, 300.0, 0.0, 0.5)

    # Section 4 — Run Replacement
    st.header("4. Run Replacement")
    run_btn = st.button("🔄 Replace Object", type="primary", use_container_width=True)

    if run_btn and video_path and replace_path:
        from pipeline.video_processor import process_video
        spinner_msg = "Processing (SD + ControlNet)..." if mode == "AI (SD + ControlNet)" else "Processing... (detecting, tracking, compositing)"
        with st.spinner(spinner_msg):
            try:
                out_path = tempfile.mktemp(suffix=".mp4")
                process_video(
                    video_path=video_path,
                    replacement_path=replace_path,
                    output_path=out_path,
                    clip_duration=float(clip_duration),
                    start_time=start_time,
                    object_type=object_type.lower(),
                    use_diffusion=(mode == "AI (SD + ControlNet)"),
                )
                st.session_state["output_video"] = out_path
                st.session_state["original_video"] = video_path
                st.success("Done! Scroll down to see results.")
            except Exception as e:
                st.error(f"Error: {e}")
                if "output_video" in st.session_state:
                    del st.session_state["output_video"]

    # Section 5 — Results
    st.header("5. Results")
    if "output_video" in st.session_state and os.path.exists(st.session_state["output_video"]):
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Original")
            st.video(st.session_state.get("original_video", ""))
        with col2:
            st.subheader("Modified")
            st.video(st.session_state["output_video"])
        st.download_button(
            "⬇️ Download Modified Video",
            data=open(st.session_state["output_video"], "rb").read(),
            file_name="chameleon_output.mp4",
            mime="video/mp4",
            use_container_width=True,
        )
    else:
        st.info("Run the replacement above to see results here.")


if __name__ == "__main__":
    main()
