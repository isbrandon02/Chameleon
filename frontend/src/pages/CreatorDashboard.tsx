import { useAuth0 } from "@auth0/auth0-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Upload } from "lucide-react";
import PageShell from "@/components/PageShell";
import VideoCard from "@/components/VideoCard";
import { deleteVideo, getCreatorVideos, getStreamUrl, getVideoOffers, updateVideoTitle, type VideoRecord } from "@/lib/api";

export default function CreatorDashboard() {
  const { user, getAccessTokenSilently } = useAuth0();
  const [videos, setVideos] = useState<VideoRecord[]>([]);
  const [offerCounts, setOfferCounts] = useState<Record<string, number>>({});
  const [streamUrls, setStreamUrls] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const creatorId = user?.sub ?? "";

  useEffect(() => {
    if (!creatorId) return;

    (async () => {
      try {
        const vids = await getCreatorVideos(getAccessTokenSilently, creatorId);
        setVideos(vids);

        const counts = await Promise.all(
          vids.map(async (v) => {
            try {
              const offers = await getVideoOffers(getAccessTokenSilently, v.videoId);
              return { id: v.videoId, count: offers.filter((o) => o.status === "pending").length };
            } catch {
              return { id: v.videoId, count: 0 };
            }
          })
        );
        setOfferCounts(Object.fromEntries(counts.map(({ id, count }) => [id, count])));

        const urls = await Promise.all(
          vids.map(async (v) => {
            try {
              const { streamUrl } = await getStreamUrl(getAccessTokenSilently, v.videoId);
              return { id: v.videoId, url: streamUrl };
            } catch {
              return { id: v.videoId, url: "" };
            }
          })
        );
        setStreamUrls(Object.fromEntries(urls.map(({ id, url }) => [id, url])));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load videos");
      } finally {
        setLoading(false);
      }
    })();
  }, [creatorId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleTitleChange(videoId: string, newTitle: string) {
    const updated = await updateVideoTitle(getAccessTokenSilently, videoId, newTitle);
    setVideos((prev) => prev.map((v) => (v.videoId === videoId ? { ...v, title: updated.title } : v)));
  }

  async function handleDelete(videoId: string) {
    await deleteVideo(getAccessTokenSilently, videoId);
    setVideos((prev) => prev.filter((v) => v.videoId !== videoId));
    setOfferCounts((prev) => { const next = { ...prev }; delete next[videoId]; return next; });
    setStreamUrls((prev) => { const next = { ...prev }; delete next[videoId]; return next; });
  }

  const totalOffers = Object.values(offerCounts).reduce((a, b) => a + b, 0);
  const analyzedCount = videos.filter((v) => v.status === "analyzed").length;

  return (
    <PageShell>
      <div className="mx-auto max-w-6xl px-6 pb-20 pt-10 sm:px-10">
        <div className="mb-10 flex items-end justify-between">
          <div>
            <h1 className="text-[28px] font-semibold tracking-tight">My Videos</h1>
            {!loading && videos.length > 0 && (
              <div className="mt-2 flex items-center gap-4 text-[13px] text-white/30">
                <span>{videos.length} video{videos.length !== 1 ? "s" : ""}</span>
                <span className="h-3 w-px bg-white/10" />
                <span>{analyzedCount} analyzed</span>
                {totalOffers > 0 && (
                  <>
                    <span className="h-3 w-px bg-white/10" />
                    <span className="text-[#4ADE80]">
                      {totalOffers} pending offer{totalOffers !== 1 ? "s" : ""}
                    </span>
                  </>
                )}
              </div>
            )}
          </div>

          <Link
            to="/upload"
            className="flex items-center gap-2 rounded-full bg-[#4ADE80] px-5 py-2.5 text-[13px] font-semibold text-[#0B0F0E] transition-all hover:brightness-110"
          >
            <Upload className="h-3.5 w-3.5" />
            Upload
          </Link>
        </div>

        {loading && (
          <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i}>
                <div className="w-full animate-pulse rounded-2xl bg-white/[0.04]" style={{ aspectRatio: "9/16" }} />
                <div className="mt-3 h-4 w-3/4 animate-pulse rounded bg-white/[0.04]" />
                <div className="mt-2 h-3 w-1/3 animate-pulse rounded bg-white/[0.03]" />
              </div>
            ))}
          </div>
        )}

        {error && <p className="text-[14px] text-red-400">{error}</p>}

        {!loading && !error && videos.length === 0 && (
          <div className="flex flex-col items-center py-28 text-center">
            <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-white/[0.06] bg-white/[0.03]">
              <Upload className="h-6 w-6 text-white/20" />
            </div>
            <p className="text-[15px] font-medium text-white/70">No videos yet</p>
            <p className="mt-1.5 text-[14px] text-white/30">
              Upload your first video to start getting sponsorship offers.
            </p>
            <Link
              to="/upload"
              className="mt-6 flex items-center gap-1.5 text-[14px] font-medium text-[#4ADE80] transition-colors hover:text-[#22C55E]"
            >
              Upload a video <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}

        {!loading && videos.length > 0 && (
          <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-4">
            {videos.map((v) => (
              <VideoCard
                key={v.videoId}
                video={v}
                offerCount={offerCounts[v.videoId]}
                streamUrl={streamUrls[v.videoId]}
                onTitleChange={handleTitleChange}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>
    </PageShell>
  );
}
