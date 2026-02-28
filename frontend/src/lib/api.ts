const API_BASE = import.meta.env.VITE_API_BASE as string;

type GetToken = () => Promise<string>;

async function apiFetch<T>(
  path: string,
  getToken: GetToken,
  options: RequestInit = {}
): Promise<T> {
  const token = await getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

// ---- Types ----

export interface UploadUrlResponse {
  uploadUrl: string;
  videoId: string;
}

export interface VideoRecord {
  videoId: string;
  creatorId: string;
  title: string;
  description?: string;
  s3Location: string;
  status: "uploaded" | "analyzing" | "analyzed";
  analysisReport?: AnalysisReport;
  adInsertTimecode?: string;
  createdAt: string;
}

export interface AnalysisReport {
  topics?: string[];
  hashtags?: string[];
  summary?: string;
  sentiment?: string;
  [key: string]: unknown;
}

export interface Offer {
  offerId: string;
  videoId: string;
  companyId: string;
  creatorId: string;
  proposedBudget: number;
  message?: string;
  status: "pending" | "accepted" | "rejected";
  createdAt: string;
  editStatus?: "editing" | "complete" | "error";
  editedVideoLocation?: string;
}

// ---- API calls ----

export function getUploadUrl(
  getToken: GetToken,
  params: { fileName: string; contentType: string }
): Promise<UploadUrlResponse> {
  return apiFetch<UploadUrlResponse>(
    `/videos/upload-url?fileName=${encodeURIComponent(params.fileName)}&contentType=${encodeURIComponent(params.contentType)}`,
    getToken
  );
}

export function registerVideo(
  getToken: GetToken,
  body: { videoId: string; title: string; description?: string; s3Location: string }
): Promise<VideoRecord> {
  return apiFetch<VideoRecord>("/videos", getToken, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listVideos(
  getToken: GetToken,
  status?: string
): Promise<VideoRecord[]> {
  const qs = status ? `?status=${status}` : "";
  return apiFetch<VideoRecord[]>(`/videos${qs}`, getToken);
}

export function getCreatorVideos(
  getToken: GetToken,
  creatorId: string
): Promise<VideoRecord[]> {
  return apiFetch<VideoRecord[]>(`/creators/${creatorId}/videos`, getToken);
}

export function getVideo(
  getToken: GetToken,
  videoId: string
): Promise<VideoRecord> {
  return apiFetch<VideoRecord>(`/videos/${videoId}`, getToken);
}

export function createOffer(
  getToken: GetToken,
  body: { videoId: string; proposedBudget: number; message?: string }
): Promise<Offer> {
  return apiFetch<Offer>("/offers", getToken, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getVideoOffers(
  getToken: GetToken,
  videoId: string
): Promise<Offer[]> {
  return apiFetch<Offer[]>(`/videos/${videoId}/offers`, getToken);
}

export function getStreamUrl(
  getToken: GetToken,
  videoId: string
): Promise<{ streamUrl: string }> {
  return apiFetch<{ streamUrl: string }>(`/videos/${videoId}/stream-url`, getToken);
}

export function updateOfferStatus(
  getToken: GetToken,
  offerId: string,
  status: "accepted" | "rejected"
): Promise<Offer> {
  return apiFetch<Offer>(`/offers/${offerId}`, getToken, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export function getAcceptedOffers(getToken: GetToken): Promise<Offer[]> {
  return apiFetch<Offer[]>("/offers/accepted", getToken);
}

export function getEditedStreamUrl(
  getToken: GetToken,
  offerId: string
): Promise<{ streamUrl: string }> {
  return apiFetch<{ streamUrl: string }>(
    `/offers/${offerId}/edited-stream-url`,
    getToken
  );
}
