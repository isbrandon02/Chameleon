# Chameleon — AWS Sponsorship Marketplace

## Project Summary

An **AWS-native sponsorship marketplace** connecting:
- **Creators** who upload videos
- **Companies** who want to sponsor relevant videos

Videos are automatically analyzed via an **event-driven AI pipeline**. Results are stored in DynamoDB for sponsorship decision-making. Architecture follows AWS Well-Architected Framework principles.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React → S3 (static hosting) → CloudFront CDN |
| Backend | FastAPI → AWS Elastic Beanstalk (Python platform) |
| Storage | Amazon S3 (videos, thumbnails, AI JSON) |
| Database | Amazon DynamoDB |
| Events | Amazon EventBridge + AWS Lambda |
| Orchestration | AWS Step Functions (optional) |

---

## Core System Flows

### 1. Creator Upload Flow
1. Creator logs in via React frontend
2. Frontend calls FastAPI → requests pre-signed S3 URL
3. FastAPI generates pre-signed URL via AWS SDK
4. Frontend uploads video **directly to S3** (FastAPI not involved in transfer)
5. FastAPI writes to DynamoDB: `{ videoId, creatorId, s3Location, status: "uploaded" }`
6. S3 `ObjectCreated` event fires → EventBridge

### 2. AI Analysis Flow (Event-Driven)
1. EventBridge rule matches S3 event
2. Triggers Lambda (directly) OR Step Functions workflow
3. Lambda:
   - Retrieves S3 object metadata
   - Calls external video analysis API (e.g., TwelveLabs)
   - Writes analysis results to DynamoDB
   - Updates `status = "analyzed"`
4. **FastAPI is NOT involved in video processing**

### 3. Sponsorship Marketplace Flow
- **Company:** browses analyzed videos → submits sponsorship offer
- **Creator:** reviews offer → accepts or rejects
- **FastAPI handles:** offer creation, status updates, DynamoDB persistence
- **No AI processing** during offer handling

---

## DynamoDB Data Model

### `Creators` Table
- **PK:** `creatorId`
- Fields: profile info, niche/category, metrics (optional)

### `Companies` Table
- **PK:** `companyId`
- Fields: brand info, product category, budget range

### `Videos` Table
- **PK:** `videoId`
- **GSI:** `creatorId`
- Fields: `s3Location`, `status` (uploaded | analyzing | analyzed), `analysisReport` (JSON), `createdAt`

### `Offers` Table
- **PK:** `offerId`
- **GSI:** `videoId`
- Fields: `companyId`, `creatorId`, `proposedBudget`, `status` (pending | accepted | rejected), timestamps

---

## Service Responsibilities

### React (Frontend)
- UI rendering, API calls, dashboard display
- File upload via pre-signed S3 URLs
- **Must NOT:** process video files or access DynamoDB directly

### FastAPI (Backend)
- Auth (JWT), pre-signed S3 URL generation
- CRUD: Creators, Companies, Videos, Offers
- DynamoDB queries, return AI analysis data
- **Must NOT:** perform long-running video analysis or block on AI processing

### Lambda
- Triggered by EventBridge
- Calls video analysis API, writes results to DynamoDB
- **Must be idempotent** and handle retries safely

### Step Functions (Optional)
- Orchestrates multi-step Lambda processing
- Manages retries and exposes workflow state

---

## IAM Roles (Least Privilege)

| Service | Permissions |
|---|---|
| FastAPI | DynamoDB read/write, S3 generate pre-signed URLs |
| Lambda | S3 read objects, DynamoDB write |

---

## Environment Variables

```
AWS_REGION
S3_BUCKET_NAME
DYNAMODB_TABLE_NAMES
VIDEO_ANALYSIS_API_KEY
JWT_SECRET
```

---

## Key Constraints

- All large file uploads go **directly to S3** (never through FastAPI)
- No custom EC2, Kubernetes, self-managed DBs, or GPU workloads in Lambda
- Never expose AWS credentials to the frontend
- Use pre-signed URLs for all uploads
- Enable CORS correctly on S3
- Use HTTPS via CloudFront and Elastic Beanstalk load balancer

---

## Error Handling

- Lambda must handle API failures with **retries**
- DynamoDB updates should use **conditional writes** where possible
- Step Functions (if used) must include **retry policies**

---

## Scalability Notes

- S3: auto-scales
- DynamoDB: use **on-demand capacity** (recommended for hackathon)
- Lambda: auto-scales with events
- Elastic Beanstalk: auto-scaling enabled

---

## Future Extensions (Out of Scope)

- Brand matching engine
- Real-time video analysis
- AWS Cognito authentication
- Regional ad targeting
- Multi-tenant separation
