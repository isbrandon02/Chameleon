import { useAuth0 } from "@auth0/auth0-react";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Check, ImagePlus, X } from "lucide-react";
import PageShell from "@/components/PageShell";
import {
  createOffer,
  getProductImageUploadUrl,
  getProductImageUrl,
  getStreamUrl,
  getVideo,
  getVideoOffers,
  updateOfferStatus,
  type Offer,
  type VideoRecord,
} from "@/lib/api";

const ROLES_CLAIM = "https://chameleon.com/roles";

const statusStyles: Record<string, string> = {
  uploaded: "bg-amber-400/10 text-amber-400",
  analyzing: "bg-blue-400/10 text-blue-400",
  analyzed: "bg-[#4ADE80]/10 text-[#4ADE80]",
  pending: "bg-amber-400/10 text-amber-400",
  accepted: "bg-[#4ADE80]/10 text-[#4ADE80]",
  rejected: "bg-red-400/10 text-red-400",
};

export default function VideoDetail() {
  const { videoId } = useParams<{ videoId: string }>();
  const { user, getAccessTokenSilently } = useAuth0();

  const [video, setVideo] = useState<VideoRecord | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [offerBudget, setOfferBudget] = useState("");
  const [offerMessage, setOfferMessage] = useState("");
  const [productImageFile, setProductImageFile] = useState<File | null>(null);
  const [productImagePreview, setProductImagePreview] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [offerImages, setOfferImages] = useState<Record<string, string>>({});

  const roles = ((user?.[ROLES_CLAIM] as string[] | undefined) ?? []).map((r) =>
    r.toLowerCase()
  );
  const isCompany = roles.includes("company");
  const isCreator = roles.includes("creator");

  async function loadData() {
    if (!videoId) return;
    try {
      const [vid, offs, stream] = await Promise.all([
        getVideo(getAccessTokenSilently, videoId),
        getVideoOffers(getAccessTokenSilently, videoId),
        getStreamUrl(getAccessTokenSilently, videoId),
      ]);
      setVideo(vid);
      setOffers(offs);
      setStreamUrl(stream.streamUrl);
      await loadOfferImages(offs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [videoId]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleImageSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setProductImageFile(file);
    setProductImagePreview(URL.createObjectURL(file));
  }

  function handleRemoveImage() {
    setProductImageFile(null);
    setProductImagePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function loadOfferImages(offerList: Offer[]) {
    const withImages = offerList.filter((o) => o.productImageUrl);
    const results = await Promise.all(
      withImages.map(async (o) => {
        try {
          const { url } = await getProductImageUrl(getAccessTokenSilently, o.productImageUrl!);
          return { offerId: o.offerId, url };
        } catch {
          return null;
        }
      })
    );
    const map: Record<string, string> = {};
    for (const r of results) if (r) map[r.offerId] = r.url;
    setOfferImages(map);
  }

  async function handleMakeOffer(e: React.FormEvent) {
    e.preventDefault();
    if (!videoId) return;
    setSubmitting(true);
    try {
      let productImageUrl: string | undefined;
      if (productImageFile) {
        const { uploadUrl, s3Url } = await getProductImageUploadUrl(getAccessTokenSilently, {
          fileName: productImageFile.name,
          contentType: productImageFile.type || "image/jpeg",
        });
        await fetch(uploadUrl, {
          method: "PUT",
          body: productImageFile,
          headers: { "Content-Type": productImageFile.type || "image/jpeg" },
        });
        productImageUrl = s3Url;
      }
      await createOffer(getAccessTokenSilently, {
        videoId,
        proposedBudget: parseFloat(offerBudget),
        message: offerMessage.trim() || undefined,
        productImageUrl,
      });
      toast.success("Offer submitted!");
      setDialogOpen(false);
      setOfferBudget("");
      setOfferMessage("");
      handleRemoveImage();
      await loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to submit offer");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleOfferAction(offerId: string, status: "accepted" | "rejected") {
    try {
      await updateOfferStatus(getAccessTokenSilently, offerId, status);
      toast.success(`Offer ${status}`);
      await loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update offer");
    }
  }

  if (loading) {
    return (
      <PageShell>
        <div className="mx-auto max-w-4xl px-6 py-10 sm:px-10">
          <div className="h-8 w-2/3 animate-pulse rounded bg-white/[0.04]" />
          <div className="mt-4 h-4 w-full animate-pulse rounded bg-white/[0.04]" />
          <div className="mt-6 aspect-video w-full animate-pulse rounded-2xl bg-white/[0.04]" />
        </div>
      </PageShell>
    );
  }

  if (error || !video) {
    return (
      <PageShell>
        <div className="mx-auto max-w-4xl px-6 py-10 sm:px-10">
          <p className="text-[14px] text-red-400">{error ?? "Video not found"}</p>
        </div>
      </PageShell>
    );
  }

  const report = video.analysisReport;

  return (
    <PageShell>
      <div className="mx-auto max-w-4xl space-y-8 px-6 pb-20 pt-10 sm:px-10">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[28px] font-semibold tracking-tight">{video.title}</h1>
            {video.description && (
              <p className="mt-2 text-[15px] text-white/35">{video.description}</p>
            )}
            <div className="mt-3 flex items-center gap-3">
              <span className="text-[12px] text-white/25">
                {new Date(video.createdAt).toLocaleDateString()}
              </span>
              <span
                className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${statusStyles[video.status] ?? "bg-white/[0.06] text-white/40"}`}
              >
                {video.status}
              </span>
            </div>
          </div>

          {isCompany && video.status === "analyzed" && (
            <button
              onClick={() => setDialogOpen(true)}
              className="flex-shrink-0 rounded-full bg-[#4ADE80] px-5 py-2.5 text-[13px] font-semibold text-[#0B0F0E] transition-all hover:brightness-110"
            >
              Make Offer
            </button>
          )}
        </div>

        {streamUrl && (
          <video
            src={streamUrl}
            controls
            className="w-full rounded-2xl border border-white/[0.04] bg-black"
            style={{ maxHeight: "480px" }}
          />
        )}

        {video.adInsertTimecode && (
          <div className="rounded-2xl border border-[#4ADE80]/10 bg-[#4ADE80]/[0.04] px-5 py-4">
            <span className="text-[13px] font-medium text-[#4ADE80]/70">
              Optimal placement window
            </span>
            <span className="ml-2 font-mono text-[14px] text-white/70">
              {video.adInsertTimecode}
            </span>
          </div>
        )}

        {report && (
          <div className="rounded-2xl border border-white/[0.04] bg-white/[0.02] p-6">
            <h2 className="mb-4 text-[15px] font-semibold text-white/70">Analysis</h2>
            <div className="space-y-4">
              {report.summary && (
                <p className="text-[14px] leading-relaxed text-white/40">{report.summary}</p>
              )}
              {report.topics && report.topics.length > 0 && (
                <div>
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.1em] text-white/25">
                    Topics
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {report.topics.map((t) => (
                      <span key={t} className="rounded-full bg-white/[0.04] px-3 py-1 text-[12px] text-white/40">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {report.hashtags && report.hashtags.length > 0 && (
                <div>
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.1em] text-white/25">
                    Hashtags
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {report.hashtags.map((h) => (
                      <span key={h} className="text-[13px] text-white/25">#{h}</span>
                    ))}
                  </div>
                </div>
              )}
              {report.sentiment && (
                <p className="text-[14px] text-white/40">
                  <span className="font-medium text-white/60">Sentiment:</span> {report.sentiment}
                </p>
              )}
            </div>
          </div>
        )}

        {isCreator && (
          <div className="rounded-2xl border border-white/[0.04] bg-white/[0.02] p-6">
            <h2 className="mb-4 text-[15px] font-semibold text-white/70">Sponsorship Offers</h2>
            {offers.length === 0 ? (
              <p className="text-[14px] text-white/25">No offers yet.</p>
            ) : (
              <div className="space-y-3">
                {offers.map((o) => (
                  <div
                    key={o.offerId}
                    className="flex items-start justify-between rounded-xl border border-white/[0.04] bg-white/[0.02] p-4"
                  >
                    <div className="flex min-w-0 flex-1 gap-3">
                      {offerImages[o.offerId] && (
                        <img
                          src={offerImages[o.offerId]}
                          alt="Product"
                          className="h-14 w-14 shrink-0 rounded-lg object-cover"
                        />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-3">
                          <span className="text-[14px] font-medium text-white/70">
                            ${o.proposedBudget.toLocaleString()}
                          </span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusStyles[o.status] ?? "bg-white/[0.06] text-white/40"}`}
                          >
                            {o.status}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[12px] text-white/25">
                          {o.companyName || o.companyId}
                        </p>
                        {o.message && (
                          <p className="mt-1 truncate text-[13px] text-white/25">{o.message}</p>
                        )}
                      </div>
                    </div>

                    {o.status === "pending" && (
                      <div className="ml-4 flex gap-2">
                        <button
                          onClick={() => handleOfferAction(o.offerId, "accepted")}
                          className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#4ADE80]/10 text-[#4ADE80] transition-colors hover:bg-[#4ADE80]/20"
                        >
                          <Check className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleOfferAction(o.offerId, "rejected")}
                          className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-400/10 text-red-400 transition-colors hover:bg-red-400/20"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {dialogOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="mx-4 w-full max-w-md rounded-2xl border border-white/[0.06] bg-[#111916] p-6">
              <h3 className="mb-5 text-[18px] font-semibold tracking-tight">
                Submit Sponsorship Offer
              </h3>
              <form onSubmit={handleMakeOffer} className="space-y-5">
                <div>
                  <label className="mb-2 block text-[13px] font-medium text-white/50">
                    Budget (USD)
                  </label>
                  <input
                    type="number"
                    min="1"
                    step="0.01"
                    value={offerBudget}
                    onChange={(e) => setOfferBudget(e.target.value)}
                    placeholder="500"
                    required
                    disabled={submitting}
                    className="w-full rounded-xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 text-[14px] text-white placeholder-white/20 outline-none focus:border-[#4ADE80]/30 disabled:opacity-50"
                  />
                </div>
                <div>
                  <label className="mb-2 block text-[13px] font-medium text-white/50">
                    Message
                  </label>
                  <textarea
                    value={offerMessage}
                    onChange={(e) => setOfferMessage(e.target.value)}
                    placeholder="Tell the creator about your brand"
                    rows={3}
                    disabled={submitting}
                    className="w-full resize-none rounded-xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 text-[14px] text-white placeholder-white/20 outline-none focus:border-[#4ADE80]/30 disabled:opacity-50"
                  />
                </div>
                <div>
                  <label className="mb-2 block text-[13px] font-medium text-white/50">
                    Product Image <span className="text-white/25">(optional)</span>
                  </label>
                  {productImagePreview ? (
                    <div className="relative inline-block">
                      <img
                        src={productImagePreview}
                        alt="Product preview"
                        className="h-24 w-24 rounded-xl object-cover"
                      />
                      <button
                        type="button"
                        onClick={handleRemoveImage}
                        className="absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-[#111916] border border-white/[0.1] text-white/50 hover:text-white"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="flex items-center gap-2 rounded-xl border border-dashed border-white/[0.1] px-4 py-3 text-[13px] text-white/30 transition-colors hover:border-white/20 hover:text-white/50"
                    >
                      <ImagePlus className="h-4 w-4" />
                      Upload product image
                    </button>
                  )}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={handleImageSelect}
                  />
                </div>

                <div className="flex gap-3">
                  <button
                    type="submit"
                    disabled={submitting}
                    className="flex-1 rounded-xl bg-[#4ADE80] py-3 text-[14px] font-semibold text-[#0B0F0E] transition-all hover:brightness-110 disabled:opacity-50"
                  >
                    {submitting ? "Submitting..." : "Submit Offer"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setDialogOpen(false)}
                    className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-5 py-3 text-[14px] font-medium text-white/50 transition-colors hover:text-white"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </PageShell>
  );
}
