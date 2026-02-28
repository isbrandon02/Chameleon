# Chameleon — AWS Integration Guide

All AWS infrastructure is provisioned and live. This doc tells each team what they need to connect.

---

## AWS Resources Summary

| Resource | Name / URL |
|---|---|
| **API Gateway (HTTPS — use this)** | `https://uw88poluwh.execute-api.us-east-1.amazonaws.com` |
| **EB backend (internal only)** | `http://chameleon-prod.eba-k4tw8ws9.us-east-1.elasticbeanstalk.com` |
| **CloudFront (frontend CDN)** | `https://d3dwkbjj9nrcpp.cloudfront.net` |
| **S3 video bucket** | `chameleon-videos-730335328499` (us-east-1) |
| **S3 frontend bucket** | `chameleon-frontend-730335328499` (us-east-1) |
| **DynamoDB tables** | `videos`, `offers`, `creators`, `companies` |
| **Lambda — video analyzer** | `chameleon-video-analyzer` — fires on S3 upload, calls TwelveLabs gist, writes topics/hashtags to DynamoDB |
| **Lambda — ad analyzer** | `chameleon-ad-analyzer` — finds branded product timestamps via TwelveLabs analyze_stream, writes `adInsertTimecode` to DynamoDB |
| **EventBridge rule** | `chameleon-s3-upload-rule` → triggers `chameleon-video-analyzer` on `videos/` uploads |

---

## FastAPI Backend Team

The FastAPI backend is already written and deployed (`backend/main.py`). To modify and redeploy:

### Deploying to Elastic Beanstalk

```bash
# Install EB CLI if you don't have it
pip install awsebcli

# From the backend/ directory
eb init chameleon --platform python-3.12 --region us-east-1 --profile chameleon
eb deploy chameleon-prod --profile chameleon
```

### Required files (already in backend/)

**`Procfile`** — tells EB how to start the app:
```
web: gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
```

**`GET /health`** — required by EB health checks:
```python
@app.get("/health")
def health():
    return {"status": "ok"}
```

**`.ebextensions/options.config`** — injects env vars into EB:
```yaml
option_settings:
  aws:elasticbeanstalk:application:environment:
    AWS_REGION: us-east-1
    S3_BUCKET_NAME: chameleon-videos-730335328499
    AUTH0_DOMAIN: dev-n8safte6j1odv3jb.us.auth0.com
    AUTH0_AUDIENCE: https://api.chameleon.com
```

### DynamoDB Tables & Indexes

boto3 picks up credentials from the EC2 instance profile automatically on EB — no explicit credentials needed.

```python
import boto3
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

videos    = dynamodb.Table("videos")    # PK: videoId  | GSI: creatorId-index
offers    = dynamodb.Table("offers")    # PK: offerId   | GSI: videoId-index
creators  = dynamodb.Table("creators")  # PK: creatorId
companies = dynamodb.Table("companies") # PK: companyId
```

### Pre-signed S3 URLs

The IAM role on EB already has `s3:PutObject` / `s3:GetObject` on the video bucket.

```python
s3 = boto3.client("s3", region_name="us-east-1")

# Upload URL (for creators)
url = s3.generate_presigned_url(
    "put_object",
    Params={"Bucket": "chameleon-videos-730335328499", "Key": f"videos/{creator_id}/{video_id}.mp4"},
    ExpiresIn=3600,
)

# Stream URL (for playback)
url = s3.generate_presigned_url(
    "get_object",
    Params={"Bucket": "chameleon-videos-730335328499", "Key": s3_key},
    ExpiresIn=3600,
)
```

**Important:** S3 keys for videos must start with `videos/` — EventBridge only triggers Lambda for that prefix.

### S3 Key Convention

```
videos/{creatorId}/{videoId}.{ext}
```

Note: Auth0 user IDs contain `|` which gets URL-encoded to `%7C` in presigned URLs. Always `unquote()` the path when parsing back to an S3 key:
```python
from urllib.parse import urlparse, unquote
s3_key = unquote(urlparse(s3_location).path.lstrip("/"))
```

---

## React Frontend Team

The React frontend is already built and deployed (`frontend/`). To modify and redeploy:

### Prerequisites

1. **Node.js + npm** — [nodejs.org](https://nodejs.org)
2. **AWS CLI** — [Install guide](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html), then configure the `chameleon` profile:
   ```bash
   aws configure --profile chameleon
   # AWS Access Key ID: <get from Andy>
   # AWS Secret Access Key: <get from Andy>
   # Default region: us-east-1
   # Default output format: json
   ```
3. **`frontend/.env`** — gitignored, get from Andy. Should contain:
   ```
   VITE_AUTH0_DOMAIN=dev-n8safte6j1odv3jb.us.auth0.com
   VITE_AUTH0_CLIENT_ID=jeYfrcx27JDXTjH7s9uTwPk8o0yb1Mhp
   VITE_AUTH0_AUDIENCE=https://api.chameleon.com
   VITE_API_BASE=https://uw88poluwh.execute-api.us-east-1.amazonaws.com
   ```

### Connecting to the Backend

All API calls go through API Gateway (HTTPS). The `frontend/.env` is already configured:

```
VITE_API_BASE=https://uw88poluwh.execute-api.us-east-1.amazonaws.com
```

**Do not use the EB URL directly** — it is HTTP only and will be blocked by browsers as mixed content from the HTTPS CloudFront site.

### Deploying to CloudFront / S3

```bash
cd frontend/

# Build
npm run build

# Sync to S3
aws --profile chameleon s3 sync dist/ s3://chameleon-frontend-730335328499 --delete

# Invalidate CloudFront cache (required — otherwise users see the old version)
aws --profile chameleon cloudfront create-invalidation \
  --distribution-id E1EXH8WJ778X51 \
  --paths "/*"
```

CloudFront propagation takes ~1–2 minutes after invalidation.

### Auth0

The frontend uses Auth0 for authentication. Credentials are in `frontend/.env`:
- `VITE_AUTH0_DOMAIN`
- `VITE_AUTH0_CLIENT_ID`
- `VITE_AUTH0_AUDIENCE`

User roles (`creator` or `company`) must be set as a custom claim `https://chameleon.com/roles` in the Auth0 token via an Auth0 Action.

---

## Lambda / AI Team

Two Lambda functions handle video analysis. Both use the same IAM role (`chameleon-lambda-role`) and TwelveLabs API key.

### chameleon-video-analyzer

**Trigger:** EventBridge fires automatically on every S3 `ObjectCreated` event under `videos/`
**What it does:** Calls TwelveLabs `/gist` to extract topics, hashtags, and title → writes `analysisReport` + `status=analyzed` to DynamoDB `videos` table
**Code:** `backend/handler.py`

#### Deploying

```bash
cd backend/
pip install -r requirements.txt -t pkg/ --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all: --implementation cp
cp handler.py pkg/
cd pkg && zip -r ../function.zip . -x "*.pyc" -x "__pycache__/*"

aws --profile chameleon lambda update-function-code \
  --function-name chameleon-video-analyzer \
  --zip-file fileb://../function.zip \
  --region us-east-1
```

### chameleon-ad-analyzer

**Trigger:** Manual invocation or EventBridge OfferAccepted event (to be wired up)
**What it does:** Downloads video from S3, uploads to TwelveLabs, runs `analyze_stream` with a branded product detection prompt → writes `adInsertTimecode` (e.g. `"0:07-0:23"`) to DynamoDB `videos` table
**Code:** `backend/ad_analyzer.py`

#### Deploying

```bash
cd backend/
pip install twelvelabs boto3 -t pkg/ --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all: --implementation cp
cp ad_analyzer.py pkg/
cd pkg && zip -r ../function.zip . -x "*.pyc" -x "__pycache__/*"

aws --profile chameleon lambda update-function-code \
  --function-name chameleon-ad-analyzer \
  --zip-file fileb://../function.zip \
  --region us-east-1
```

#### Manual test invocation

```bash
aws --profile chameleon lambda invoke \
  --function-name chameleon-ad-analyzer \
  --payload '{"videoId":"<videoId>"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 \
  output.json && cat output.json
```

### Environment Variables (already set)

| Variable | Function | Value |
|---|---|---|
| `VIDEO_ANALYSIS_API_KEY` | `chameleon-video-analyzer` | TwelveLabs API key (set) |
| `TL_API_KEY` | `chameleon-ad-analyzer` | TwelveLabs API key (set) |
| `TL_INDEX_ID` | `chameleon-ad-analyzer` | `69a24da4765e515a4f6b1b5f` (set) |
| `S3_BUCKET_NAME` | `chameleon-ad-analyzer` | `chameleon-videos-730335328499` (set) |

### DynamoDB `videos` Table — Status Flow

```
uploaded  →  analyzing  →  analyzed
                        →  error
```

`status=uploaded` is written by FastAPI when video metadata is registered. `chameleon-video-analyzer` reads this and conditionally moves it forward (idempotency guard: only processes `uploaded` records).

`adInsertTimecode` is written separately by `chameleon-ad-analyzer` and does not affect the status field.

---

## IAM Roles (Already Configured)

| Role | Used By | Permissions |
|---|---|---|
| `chameleon-lambda-role` | Both Lambdas | `s3:GetObject` on video bucket; `dynamodb:GetItem/PutItem/UpdateItem` on `videos` table |
| `aws-elasticbeanstalk-ec2-role` | EB EC2 instances | DynamoDB CRUD on all 4 tables + indexes; `s3:PutObject/GetObject` on video bucket |

---

## AWS Profile

All commands use `--profile chameleon` and `--region us-east-1`.
Account ID: `730335328499`
