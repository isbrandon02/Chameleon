# Chameleon — Seamless AI Ad Integration for Creator Videos

Chameleon uses AI to seamlessly integrate sponsor products directly into creator videos — making ads feel like a natural part of the content rather than an interruption. Brands submit their product, AI identifies the optimal placement window in the video, and Runway ML generates a photorealistic edited version with the product blended in.

**Built at CUHackit 2026**

---

## The Problem

Traditional sponsorships are jarring — creators stop mid-video to hold up a product. Viewers skip it. Brands get low engagement. Chameleon makes sponsorships invisible: the product appears naturally in the scene, at the right moment, without breaking the flow of the content.

---

## How It Works

1. **Creator uploads a video** — stored directly in S3
2. **TwelveLabs AI analyzes the video** — extracting topics, hashtags, sentiment, and identifying the optimal ad placement timecodes
3. **Brands browse and make offers** — attaching their product image and budget
4. **Creator accepts** — triggering the automated editing pipeline
5. **Runway ML generates the sponsored version** — the product is integrated into the scene at the AI-identified placement window, preserving lighting, motion, and context
6. **Both parties view the result** — the final edited video appears on the Sponsored Videos page

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui |
| Auth | Auth0 (Google OAuth, role-based: creator / company) |
| Backend | FastAPI → AWS Elastic Beanstalk (Python 3.12) |
| Storage | Amazon S3 (videos, product images, edited videos) |
| Database | Amazon DynamoDB |
| Events | Amazon EventBridge + AWS Lambda |
| Video Analysis | TwelveLabs API (topics, hashtags, sentiment, ad timing) |
| Video Editing | Runway ML (AI-powered seamless product integration) |
| CDN | Amazon CloudFront |

---

## Architecture

```
Creator uploads video
        │
        ▼
    Amazon S3
        │
        ▼
  EventBridge rule
        │
        ├──► Lambda: chameleon-video-analyzer
        │         └─ TwelveLabs → topics, hashtags, sentiment → DynamoDB
        │
        └──► Lambda: chameleon-ad-analyzer
                  └─ Detects optimal ad placement timecodes → DynamoDB

Brand makes offer (with product image) → FastAPI → DynamoDB
Creator accepts → FastAPI → EventBridge (OfferAccepted)
        │
        ▼
Lambda: chameleon-video-edit
        └─ Downloads video + product image from S3
        └─ Runway ML seamlessly integrates product at the AI-identified timecode
        └─ Uploads edited video to S3
        └─ Updates DynamoDB (editStatus=complete)
```

---

---

## Project Structure

```
Chameleon/
├── frontend/               # React app (Vite + Tailwind)
│   └── src/
│       ├── pages/
│       │   ├── Landing.tsx
│       │   ├── CreatorDashboard.tsx
│       │   ├── UploadVideo.tsx
│       │   ├── CompanyBrowse.tsx
│       │   ├── VideoDetail.tsx
│       │   └── SponsoredVideos.tsx
│       ├── components/
│       │   ├── Navbar.tsx
│       │   ├── PageShell.tsx
│       │   ├── VideoCard.tsx
│       │   └── ProtectedRoute.tsx
│       └── lib/
│           └── api.ts
├── backend/
│   ├── main.py             # FastAPI app (Elastic Beanstalk)
│   ├── handler.py          # Lambda 1: TwelveLabs video analysis
│   ├── ad_analyzer.py      # Lambda 2: Ad placement timecode detection
│   └── video_edit_lambda.py # Lambda 3: Runway ML video editing
└── infra/
    └── integration.md      # AWS infrastructure guide
```

---

## Key Features

- **AI placement detection** — TwelveLabs identifies the exact moment in a video where a product can be naturally inserted
- **Runway ML integration** — photorealistic product placement that matches the scene's lighting, motion, and context
- **Product image uploads** — brands attach their product photo when making an offer
- **End-to-end automated pipeline** — from offer acceptance to finished edited video with no manual steps
- **Role-based access** — separate creator and brand experiences
- **Direct S3 uploads** — videos never pass through the backend server
- **Secure media delivery** — all video playback via time-limited S3 presigned URLs

---

## AWS Resources

| Resource | Name |
|---|---|
| S3 Video Bucket | `chameleon-videos-730335328499` |
| S3 Frontend Bucket | `chameleon-frontend-730335328499` |
| CloudFront | `E1EXH8WJ778X51` |
| Elastic Beanstalk | `chameleon` / `chameleon-prod` |
| DynamoDB Tables | `videos`, `offers`, `creators`, `companies` |
| Lambda Functions | `chameleon-video-analyzer`, `chameleon-ad-analyzer`, `chameleon-video-edit` |
| EventBridge Rules | `chameleon-s3-upload-rule`, `chameleon-offer-accepted-rule` |
