import os
import re
import requests
from dotenv import load_dotenv

# import the helper that indexes & searches videos
from twelve_labs import add_video, delete_video

load_dotenv()

RUNWAY_API_KEY = os.environ.get("RUNWAY_API_KEY")
# you can configure a default model here or pass it as an argument
RUNWAY_MODEL = os.environ.get("RUNWAY_MODEL", "your-model-id")

if not RUNWAY_API_KEY:
    raise RuntimeError("RUNWAY_API_KEY environment variable is not set; export it or source your .env")

RUNWAY_BASE_URL = "https://api.runwayml.com/v1"  # change if needed


def parse_timestamps(text):
    """Parse timestamps from the string returned by twelve_labs.

    The TwelveLabs query is instructed to print start and end timestamps only,
    so we look for pairs of timecodes separated by a dash. Example output:
        00:00:05 - 00:00:12
        1:02-1:09
    The function normalises them to seconds (float) and returns a list of
    (start_seconds, end_seconds) tuples.
    """
    # simple regex to match hh:mm:ss or mm:ss or variants
    pattern = r"(\d{1,2}(?::\d{2}){1,2})\s*-\s*(\d{1,2}(?::\d{2}){1,2})"
    matches = re.findall(pattern, text)
    result = []
    for start, end in matches:
        result.append((to_seconds(start), to_seconds(end)))
    return result


def to_seconds(timestamp):
    """Convert a timestamp like "1:23:45" or "3:21" to seconds."""
    parts = [int(p) for p in timestamp.split(":")]
    if len(parts) == 3:
        h, m, s = parts
        return h * 3600 + m * 60 + s
    elif len(parts) == 2:
        m, s = parts
        return m * 60 + s
    else:
        return parts[0]


def call_runway(video_path, start_sec, end_sec, model_id=None):
    """Send the clip defined by start_sec/end_sec to a Runway model.

    This is a very simple wrapper; depending on the model you may need to
    stream the entire file and provide the range in the JSON body or pre-
    cut the clip yourself and upload the subclip. Here we simply POST the
    full video with a `start`/`end` field so it can be trimmed server-side.
    """
    if model_id is None:
        model_id = RUNWAY_MODEL

    url = f"{RUNWAY_BASE_URL}/models/{model_id}/outputs"
    headers = {
        "Authorization": f"Bearer {RUNWAY_API_KEY}",
    }

    # we assume the API accepts multipart/form-data with the file
    # along with a JSON field describing the start/end times
    with open(video_path, "rb") as f:
        files = {"file": f}
        data = {"start": start_sec, "end": end_sec}
        resp = requests.post(url, headers=headers, files=files, data=data)

    resp.raise_for_status()
    return resp.json()


def process_video(video_file, query, runway_model=None):
    """Top-level convenience function described by the user.

    1. Add the video to TwelveLabs index and run the `query`.
    2. Parse the returned timestamp ranges.
    3. For each range call the Runway API and collect its response.
    4. Delete the indexed asset so we don't leak data.

    Returns a tuple of (twelve_labs_id, timestamps, runway_responses).
    """
    # the add_video helper expects just a filename located in ../resources/
    # copy the file over if it's not already there.
    basename = os.path.basename(video_file)
    dest = os.path.join(os.path.dirname(__file__), "..", "resources", basename)
    if not os.path.exists(dest):
        # copy the file
        with open(video_file, "rb") as src, open(dest, "wb") as dst:
            dst.write(src.read())

    asset_id, analysis_text = add_video(basename, query)
    timestamps = parse_timestamps(analysis_text)

    runway_results = []
    for start, end in timestamps:
        runway_results.append(call_runway(dest, start, end, model_id=runway_model))

    # optionally clean up
    delete_video(asset_id)

    return asset_id, timestamps, runway_results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Index a video, run a query and then send the identified clips to Runway.")
    parser.add_argument("video", help="Path to the video file to process")
    parser.add_argument("query", help="Search query to run against TwelveLabs")
    parser.add_argument("--model", help="Runway model id to use", default=None)

    args = parser.parse_args()

    result = process_video(args.video, args.query, runway_model=args.model)
    print("Finished", result)
