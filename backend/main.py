import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, unquote

import boto3
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Chameleon API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://d3dwkbjj9nrcpp.cloudfront.net",
    ],
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# AWS clients (use EC2 instance profile on EB; env vars on local)
# ---------------------------------------------------------------------------

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "chameleon-videos-730335328499")
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "dev-n8safte6j1odv3jb.us.auth0.com")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "https://api.chameleon.com")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)
events_client = boto3.client("events", region_name=AWS_REGION)

videos_table = dynamodb.Table("videos")
offers_table = dynamodb.Table("offers")

# ---------------------------------------------------------------------------
# Auth0 JWT validation
# ---------------------------------------------------------------------------

_jwks_cache: Optional[dict] = None


async def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://{AUTH0_DOMAIN}/.well-known/jwks.json")
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token header")

    kid = unverified_header.get("kid")
    jwks = await _get_jwks()

    rsa_key = {}
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n": key["n"],
                "e": key["e"],
            }
            break

    if not rsa_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Public key not found")

    try:
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=AUTH0_AUDIENCE,
            issuer=f"https://{AUTH0_DOMAIN}/",
        )
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    roles = payload.get("https://chameleon.com/roles", [])
    return {"sub": payload["sub"], "roles": roles, "name": payload.get("name", "")}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class RegisterVideoRequest(BaseModel):
    videoId: str
    title: str
    description: Optional[str] = None
    s3Location: str


class VideoResponse(BaseModel):
    videoId: str
    creatorId: str
    creatorName: Optional[str] = None
    title: str
    description: Optional[str] = None
    s3Location: str
    status: str
    createdAt: str
    analysisReport: Optional[dict] = None
    adInsertTimecode: Optional[str] = None


class CreateOfferRequest(BaseModel):
    videoId: str
    proposedBudget: float
    message: Optional[str] = None


class OfferResponse(BaseModel):
    offerId: str
    videoId: str
    companyId: str
    companyName: Optional[str] = None
    creatorId: str
    creatorName: Optional[str] = None
    proposedBudget: float
    message: Optional[str] = None
    status: str
    createdAt: str


class UpdateVideoRequest(BaseModel):
    title: str


class UpdateOfferRequest(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/videos/upload-url")
async def get_upload_url(
    fileName: str = Query(...),
    contentType: str = Query(...),
    user: dict = Depends(get_current_user),
):
    creator_id = user["sub"]
    video_id = str(uuid.uuid4())
    ext = fileName.rsplit(".", 1)[-1] if "." in fileName else "mp4"
    s3_key = f"videos/{creator_id}/{video_id}.{ext}"

    try:
        upload_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": S3_BUCKET,
                "Key": s3_key,
                "ContentType": contentType,
            },
            ExpiresIn=3600,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not generate upload URL: {exc}")

    return {"uploadUrl": upload_url, "videoId": video_id, "s3Key": s3_key}


@app.post("/videos", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
async def register_video(
    body: RegisterVideoRequest,
    user: dict = Depends(get_current_user),
):
    creator_id = user["sub"]
    item = {
        "videoId": body.videoId,
        "creatorId": creator_id,
        "creatorName": user.get("name", ""),
        "title": body.title,
        "description": body.description or "",
        "s3Location": body.s3Location,
        "status": "uploaded",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    try:
        videos_table.put_item(Item=item)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return item


@app.get("/videos")
async def list_videos(
    status_filter: Optional[str] = Query(None, alias="status"),
    user: dict = Depends(get_current_user),
):
    try:
        if status_filter:
            response = videos_table.scan(
                FilterExpression="#s = :s",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":s": status_filter},
            )
        else:
            response = videos_table.scan()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return response.get("Items", [])


@app.get("/videos/{videoId}", response_model=VideoResponse)
async def get_video(videoId: str, user: dict = Depends(get_current_user)):
    try:
        response = videos_table.get_item(Key={"videoId": videoId})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Video not found")
    return item


@app.get("/videos/{videoId}/stream-url")
async def get_stream_url(videoId: str, user: dict = Depends(get_current_user)):
    try:
        response = videos_table.get_item(Key={"videoId": videoId})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Video not found")

    s3_key = unquote(urlparse(item["s3Location"]).path.lstrip("/"))
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": s3_key},
            ExpiresIn=3600,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not generate stream URL: {exc}")
    return {"streamUrl": url}


@app.get("/creators/{creatorId}/videos")
async def get_creator_videos(creatorId: str, user: dict = Depends(get_current_user)):
    try:
        response = videos_table.query(
            IndexName="creatorId-index",
            KeyConditionExpression="creatorId = :cid",
            ExpressionAttributeValues={":cid": creatorId},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return response.get("Items", [])


@app.patch("/videos/{videoId}", response_model=VideoResponse)
async def update_video(
    videoId: str,
    body: UpdateVideoRequest,
    user: dict = Depends(get_current_user),
):
    try:
        resp = videos_table.get_item(Key={"videoId": videoId})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    item = resp.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Video not found")
    if item["creatorId"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    new_title = body.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    try:
        response = videos_table.update_item(
            Key={"videoId": videoId},
            UpdateExpression="SET title = :t",
            ExpressionAttributeValues={":t": new_title},
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return response["Attributes"]


@app.delete("/videos/{videoId}", status_code=204)
async def delete_video(
    videoId: str,
    user: dict = Depends(get_current_user),
):
    try:
        resp = videos_table.get_item(Key={"videoId": videoId})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    item = resp.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Video not found")
    if item["creatorId"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        videos_table.delete_item(Key={"videoId": videoId})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Best-effort S3 cleanup
    try:
        s3_key = unquote(urlparse(item["s3Location"]).path.lstrip("/"))
        s3.delete_object(Bucket=S3_BUCKET, Key=s3_key)
    except Exception:
        pass


@app.post("/offers", response_model=OfferResponse, status_code=status.HTTP_201_CREATED)
async def create_offer(
    body: CreateOfferRequest,
    user: dict = Depends(get_current_user),
):
    company_id = user["sub"]

    # Fetch video to get creatorId
    try:
        video_resp = videos_table.get_item(Key={"videoId": body.videoId})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    video = video_resp.get("Item")
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    offer_id = str(uuid.uuid4())
    item = {
        "offerId": offer_id,
        "videoId": body.videoId,
        "companyId": company_id,
        "companyName": user.get("name", ""),
        "creatorId": video["creatorId"],
        "creatorName": video.get("creatorName", ""),
        "proposedBudget": str(body.proposedBudget),
        "message": body.message or "",
        "status": "pending",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    try:
        offers_table.put_item(Item=item)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {**item, "proposedBudget": body.proposedBudget}


@app.get("/videos/{videoId}/offers")
async def get_video_offers(videoId: str, user: dict = Depends(get_current_user)):
    try:
        response = offers_table.query(
            IndexName="videoId-index",
            KeyConditionExpression="videoId = :vid",
            ExpressionAttributeValues={":vid": videoId},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return response.get("Items", [])


@app.patch("/offers/{offerId}", response_model=OfferResponse)
async def update_offer(
    offerId: str,
    body: UpdateOfferRequest,
    user: dict = Depends(get_current_user),
):
    if body.status not in ("pending", "accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid status value")
    try:
        response = offers_table.update_item(
            Key={"offerId": offerId},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": body.status},
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    item = response.get("Attributes")
    if not item:
        raise HTTPException(status_code=404, detail="Offer not found")

    # Emit EventBridge event so Lambda 3 can edit the video
    if body.status == "accepted":
        try:
            events_client.put_events(Entries=[{
                "Source": "chameleon.offers",
                "DetailType": "OfferAccepted",
                "Detail": json.dumps({
                    "offerId": offerId,
                    "videoId": item["videoId"],
                    "companyId": item["companyId"],
                    "creatorId": item["creatorId"],
                }),
                "EventBusName": "default",
            }])
        except Exception as exc:
            # Non-fatal: offer is already updated; log and continue
            print(f"[warn] EventBridge put_events failed: {exc}")

    # Convert Decimal proposedBudget back to float for response
    if "proposedBudget" in item:
        item["proposedBudget"] = float(item["proposedBudget"])
    return item


@app.get("/offers/accepted")
async def get_accepted_offers(user: dict = Depends(get_current_user)):
    """Return all accepted offers where the caller is the creator or company."""
    user_id = user["sub"]
    try:
        response = offers_table.scan(
            FilterExpression="#s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "accepted"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    items = response.get("Items", [])
    # Filter to only offers belonging to this user
    items = [
        i for i in items if i.get("creatorId") == user_id or i.get("companyId") == user_id
    ]
    for i in items:
        if "proposedBudget" in i:
            i["proposedBudget"] = float(i["proposedBudget"])
    return items


@app.get("/offers/{offerId}/edited-stream-url")
async def get_edited_stream_url(offerId: str, user: dict = Depends(get_current_user)):
    """Generate a presigned URL for the edited video associated with an accepted offer."""
    try:
        response = offers_table.get_item(Key={"offerId": offerId})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Offer not found")

    user_id = user["sub"]
    if item.get("creatorId") != user_id and item.get("companyId") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    edited_location = item.get("editedVideoLocation")
    if not edited_location:
        raise HTTPException(status_code=404, detail="Edited video not available yet")

    s3_key = unquote(urlparse(edited_location).path.lstrip("/"))
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": s3_key},
            ExpiresIn=3600,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not generate stream URL: {exc}")
    return {"streamUrl": url}
