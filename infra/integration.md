# Chameleon — AWS Integration Guide

All AWS infrastructure is provisioned and live. This doc tells each team what they need to connect.

---

## AWS Resources Summary

| Resource | Name / URL |
|---|---|
| **EB backend endpoint** | `http://chameleon-prod.eba-k4tw8ws9.us-east-1.elasticbeanstalk.com` |
| **CloudFront (frontend CDN)** | `https://d3dwkbjj9nrcpp.cloudfront.net` |
| **S3 video bucket** | `chameleon-videos-730335328499` (us-east-1) |
| **S3 frontend bucket** | `chameleon-frontend-730335328499` (us-east-1) |
| **DynamoDB tables** | `videos`, `offers`, `creators`, `companies` |
| **Lambda** | `chameleon-video-analyzer` (python3.12, 600s timeout) |
| **EventBridge rule** | `chameleon-s3-upload-rule` → triggers Lambda on `videos/` uploads |

---

## FastAPI Backend Team

### Deploying to Elastic Beanstalk

The EB application `chameleon` / environment `chameleon-prod` is ready. To deploy:

1. Install the EB CLI: `pip install awsebcli`
2. From your backend directory, initialize and deploy:
   ```bash
   eb init chameleon --platform python-3.12 --region us-east-1
   eb deploy chameleon-prod
   ```

3. Your app must include a `Procfile`:
   ```
   web: gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
   ```

4. Your app must include a `GET /health` endpoint (required by EB health checks):
   ```python
   @app.get("/health")
   def health():
       return {"status": "ok"}
   ```

### Required .ebextensions config

Include a `.ebextensions/options.config` in your project zip so EB injects env vars:

```yaml
option_settings:
  aws:elasticbeanstalk:application:environment:
    AWS_REGION: us-east-1
    S3_BUCKET_NAME: chameleon-videos-730335328499
    AUTH0_DOMAIN: REPLACE_ME
    AUTH0_AUDIENCE: REPLACE_ME
    AUTH0_CLIENT_ID: REPLACE_ME
```

**Or** set them directly after deploy (avoids committing secrets):
```bash
aws --profile chameleon elasticbeanstalk update-environment \
  --application-name chameleon \
  --environment-name chameleon-prod \
  --option-settings \
    Namespace=aws:elasticbeanstalk:application:environment,OptionName=AUTH0_DOMAIN,Value=<YOUR_DOMAIN> \
    Namespace=aws:elasticbeanstalk:application:environment,OptionName=AUTH0_AUDIENCE,Value=<YOUR_AUDIENCE> \
    --region us-east-1
```

### DynamoDB Tables & Indexes

boto3 picks up credentials from the EC2 instance profile automatically on EB — no explicit credentials needed.

```python
import boto3
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

videos   = dynamodb.Table("videos")    # PK: videoId | GSI: creatorId-index
offers   = dynamodb.Table("offers")    # PK: offerId  | GSI: videoId-index
creators = dynamodb.Table("creators")  # PK: creatorId
companies= dynamodb.Table("companies") # PK: companyId
```

### Pre-signed S3 Upload URLs

The IAM role on EB already has `s3:PutObject` / `s3:GetObject` on the video bucket.

```python
import boto3
s3 = boto3.client("s3", region_name="us-east-1")

url = s3.generate_presigned_url(
    "put_object",
    Params={"Bucket": "chameleon-videos-730335328499", "Key": f"videos/{creator_id}/{video_id}.mp4"},
    ExpiresIn=3600,
)
```

**Important:** S3 keys for videos must start with `videos/` — EventBridge only triggers Lambda for that prefix.

### S3 Key Convention

```
videos/{creatorId}/{videoId}.mp4
```

Lambda extracts `videoId` from position `[2]` of the key split by `/`.

### CORS

The video bucket has CORS configured (GET, PUT, POST, HEAD, all origins). The frontend can upload directly to S3 using the pre-signed URL — the upload should **not** go through your FastAPI server.

---

## React Frontend Team

### Connecting to the Backend

The EB endpoint is behind HTTP only. For production, point your API calls to the EB CNAME directly or set up a CloudFront behavior to proxy `/api/*` to EB.

```javascript
const API_BASE = "http://chameleon-prod.eba-k4tw8ws9.us-east-1.elasticbeanstalk.com";
```

### Deploying to CloudFront / S3

Build your React app and sync to the frontend S3 bucket:

```bash
npm run build
aws --profile chameleon s3 sync build/ s3://chameleon-frontend-730335328499 --delete
```

The CloudFront distribution `d3dwkbjj9nrcpp.cloudfront.net` serves the frontend bucket. It:
- Redirects HTTP → HTTPS
- Returns `index.html` for 404s (React Router works)
- Uses CachingOptimized policy

To invalidate CloudFront cache after a deploy:
```bash
aws --profile chameleon cloudfront create-invalidation \
  --distribution-id E1EXH8WJ778X51 \
  --paths "/*"
```

### Direct S3 Upload Flow

```javascript
// 1. Get pre-signed URL from your FastAPI backend
const { uploadUrl, videoId, s3Key } = await fetch(`${API_BASE}/videos/upload-url`, {
  method: "POST",
  headers: { Authorization: `Bearer ${token}` }
}).then(r => r.json());

// 2. Upload directly to S3 (not through FastAPI)
await fetch(uploadUrl, {
  method: "PUT",
  body: videoFile,
  headers: { "Content-Type": "video/mp4" }
});

// 3. Register the video metadata with FastAPI
await fetch(`${API_BASE}/videos`, {
  method: "POST",
  headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  body: JSON.stringify({ videoId, s3Key })
});
```

---

## Lambda / AI Team

### What's Already Wired

- Lambda function `chameleon-video-analyzer` exists (python3.12, 600s, 512MB)
- EventBridge rule fires on every `ObjectCreated` event under `videos/` in the video bucket
- Lambda has permission to be invoked by EventBridge
- Lambda IAM role has: `s3:GetObject` on video bucket + `dynamodb:GetItem/PutItem/UpdateItem` on `videos` table

### Deploying Your Handler

```bash
# From your lambda directory
pip install -r requirements.txt -t pkg/
cp handler.py pkg/
cd pkg && zip -r ../function.zip .

aws --profile chameleon lambda update-function-code \
  --function-name chameleon-video-analyzer \
  --zip-file fileb://../function.zip \
  --region us-east-1
```

### Setting the TwelveLabs API Key

```bash
aws --profile chameleon lambda update-function-configuration \
  --function-name chameleon-video-analyzer \
  --environment 'Variables={DYNAMODB_TABLE=videos,VIDEO_ANALYSIS_API_KEY=<YOUR_KEY>}' \
  --region us-east-1
```

### Expected Event Shape (from EventBridge)

```json
{
  "source": "aws.s3",
  "detail-type": "Object Created",
  "detail": {
    "bucket": { "name": "chameleon-videos-730335328499" },
    "object": { "key": "videos/{creatorId}/{videoId}.mp4" }
  }
}
```

### DynamoDB `videos` Table — Status Flow

```
uploaded  →  analyzing  →  analyzed
                        →  error
```

Write `status: "uploaded"` from FastAPI when the video metadata is registered. Lambda reads this and conditionally moves it forward (idempotency guard: only processes `uploaded` records).

---

## IAM Roles (Already Configured)

| Role | Used By | Permissions |
|---|---|---|
| `chameleon-lambda-role` | Lambda | `s3:GetObject` on video bucket; `dynamodb:GetItem/PutItem/UpdateItem` on `videos` table |
| `aws-elasticbeanstalk-ec2-role` | EB EC2 instances | DynamoDB CRUD on all 4 tables + indexes; `s3:PutObject/GetObject` on video bucket |

---

## AWS Profile

All commands use `--profile chameleon` and `--region us-east-1`.
Account ID: `730335328499`
