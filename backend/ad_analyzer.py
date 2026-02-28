"""
Chameleon — Ad Insertion Analyzer Lambda Handler

Triggered by: EventBridge OfferAccepted event, or manual invocation for testing.
Input event:  { "videoId": "<uuid>" }

Flow:
1. Fetch video record from DynamoDB → get S3 key
2. Download video from S3 to /tmp/
3. Upload to TwelveLabs and wait for indexing
4. Run analyze_stream to find branded product timestamps (ad insertion points)
5. Store adInsertTimecode in DynamoDB videos table
6. Clean up /tmp/ and TwelveLabs indexed asset
"""

import json
import logging
import os
import time
from urllib.parse import unquote, urlparse

import boto3
from twelvelabs import TwelveLabs

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
TL_API_KEY = os.environ.get("TL_API_KEY", "")
TL_INDEX_ID = os.environ.get("TL_INDEX_ID", "")  # set via env var or auto-created
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "chameleon-videos-730335328499")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)
videos_table = dynamodb.Table("videos")

AD_DETECTION_PROMPT = (
    "Identify timestamps where a visible consumer product appears, especially items that look "
    "branded or commercially packaged, such as skincare bottles, water bottles, cosmetics, "
    "food packaging, or electronics. "
    "Return only the start and end timestamps in the format: START-END (e.g. 0:12-0:18). "
    "List each timestamp range on its own line."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_s3_key(s3_location: str) -> str:
    """Extract and URL-decode the S3 key from the stored s3Location URL."""
    return unquote(urlparse(s3_location).path.lstrip("/"))


def _get_or_create_index(client: TwelveLabs) -> str:
    """Return existing TL_INDEX_ID env var, or find/create the 'chameleon' index."""
    if TL_INDEX_ID:
        return TL_INDEX_ID

    indexes = client.indexes.list()
    for idx in indexes:
        if idx.name == "chameleon":
            logger.info("Found existing TwelveLabs index: %s", idx.id)
            return idx.id

    logger.info("Creating new TwelveLabs index 'chameleon'")
    idx = client.indexes.create(
        name="chameleon",
        engines=[
            {"name": "marengo2.6", "options": ["visual", "conversation", "text_in_video", "logo"]}
        ],
        addons=["thumbnail"],
    )
    return idx.id


def _wait_for_indexing(client: TwelveLabs, index_id: str, indexed_asset_id: str) -> None:
    """Poll until the indexed asset is ready."""
    while True:
        asset = client.indexes.indexed_assets.retrieve(
            index_id=index_id,
            indexed_asset_id=indexed_asset_id,
        )
        logger.info("Indexing status: %s", asset.status)
        if asset.status == "ready":
            return
        if asset.status == "failed":
            raise RuntimeError(f"TwelveLabs indexing failed for asset {indexed_asset_id}")
        time.sleep(5)


# ---------------------------------------------------------------------------
# Lambda entrypoint
# ---------------------------------------------------------------------------


def handler(event: dict, context) -> dict:
    logger.info("Received event: %s", json.dumps(event))

    if not TL_API_KEY:
        raise EnvironmentError("TL_API_KEY is not set")

    video_id = event.get("videoId")
    if not video_id:
        return {"statusCode": 400, "body": "videoId is required"}

    # 1. Get video record from DynamoDB
    result = videos_table.get_item(Key={"videoId": video_id})
    item = result.get("Item")
    if not item:
        return {"statusCode": 404, "body": f"Video {video_id} not found in DynamoDB"}

    s3_key = _get_s3_key(item["s3Location"])
    ext = os.path.splitext(s3_key)[1] or ".mp4"
    local_path = f"/tmp/{video_id}{ext}"

    logger.info("Downloading s3://%s/%s to %s", S3_BUCKET, s3_key, local_path)
    s3.download_file(S3_BUCKET, s3_key, local_path)

    client = TwelveLabs(api_key=TL_API_KEY)
    indexed_asset_id = None

    try:
        index_id = _get_or_create_index(client)
        logger.info("Using TwelveLabs index: %s", index_id)

        # 2. Upload video to TwelveLabs
        with open(local_path, "rb") as f:
            asset = client.assets.create(method="direct", file=f)
        logger.info("Created TwelveLabs asset: %s", asset.id)

        indexed_asset = client.indexes.indexed_assets.create(
            index_id=index_id,
            asset_id=asset.id,
        )
        indexed_asset_id = indexed_asset.id
        logger.info("Created indexed asset: %s", indexed_asset_id)

        # 3. Wait for indexing
        _wait_for_indexing(client, index_id, indexed_asset_id)

        # 4. Analyze for ad insertion timestamps
        logger.info("Running ad insertion analysis for video %s", video_id)
        analysis_text = ""
        for chunk in client.analyze_stream(
            video_id=indexed_asset_id,
            prompt=AD_DETECTION_PROMPT,
        ):
            if chunk.event_type == "text_generation":
                analysis_text += chunk.text

        ad_timecode = analysis_text.strip()
        logger.info("Ad timecode result: %s", ad_timecode)

        # 5. Write result to DynamoDB
        videos_table.update_item(
            Key={"videoId": video_id},
            UpdateExpression="SET adInsertTimecode = :t",
            ExpressionAttributeValues={":t": ad_timecode},
        )
        logger.info("Stored adInsertTimecode for video %s", video_id)

        return {
            "statusCode": 200,
            "body": "Ad analysis complete",
            "videoId": video_id,
            "adInsertTimecode": ad_timecode,
        }

    finally:
        # Clean up /tmp/
        if os.path.exists(local_path):
            os.remove(local_path)
            logger.info("Cleaned up %s", local_path)

        # Clean up TwelveLabs indexed asset
        if indexed_asset_id:
            try:
                client.indexes.indexed_assets.delete(
                    index_id=index_id,
                    indexed_asset_id=indexed_asset_id,
                )
                logger.info("Deleted TwelveLabs indexed asset %s", indexed_asset_id)
            except Exception as exc:
                logger.warning("Could not delete indexed asset %s: %s", indexed_asset_id, exc)
