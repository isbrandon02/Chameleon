import { useAuth0 } from "@auth0/auth0-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Upload } from "lucide-react";
import Navbar from "@/components/Navbar";
import VideoCard from "@/components/VideoCard";
import { Skeleton } from "@/components/ui/skeleton";
import { getCreatorVideos, getStreamUrl, getVideoOffers, type VideoRecord } from "@/lib/api";

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

  const totalOffers = Object.values(offerCounts).reduce((a, b) => a + b, 0);
  const analyzedCount = videos.filter((v) => v.status === "analyzed").length;

  return (
    <div className="min-h-screen bg-white">
      <Navbar />

      <main className="mx-auto max-w-5xl px-8 pb-16">
        {/* Header */}
        <div className="mb-8 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">
              My Videos
            </h1>
            {!loading && videos.length > 0 && (
              <div className="mt-1.5 flex items-center gap-4 text-sm text-neutral-400">
                <span>{videos.length} video{videos.length !== 1 ? "s" : ""}</span>
                <span className="h-3 w-px bg-neutral-200" />
                <span>{analyzedCount} analyzed</span>
                {totalOffers > 0 && (
                  <>
                    <span className="h-3 w-px bg-neutral-200" />
                    <span className="text-violet-600">{totalOffers} pending offer{totalOffers !== 1 ? "s" : ""}</span>
                  </>
                )}
              </div>
            )}
          </div>

          <Link
            to="/upload"
            className="flex items-center gap-1.5 rounded-full bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-700"
          >
            <Upload className="h-3.5 w-3.5" />
            Upload
          </Link>
        </div>

        {/* Loading */}
        {loading && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i}>
                <Skeleton className="w-full rounded-xl" style={{ aspectRatio: "9/16" }} />
                <Skeleton className="mt-2 h-4 w-3/4 rounded" />
                <Skeleton className="mt-1 h-3 w-1/3 rounded" />
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="text-sm text-red-500">{error}</p>
        )}

        {/* Empty state */}
        {!loading && !error && videos.length === 0 && (
          <div className="flex flex-col items-center py-24 text-center">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-neutral-100">
              <Upload className="h-5 w-5 text-neutral-400" />
            </div>
            <p className="mb-1 text-sm font-medium text-neutral-900">No videos yet</p>
            <p className="mb-6 text-sm text-neutral-400">
              Upload your first video to start getting sponsorship offers.
            </p>
            <Link
              to="/upload"
              className="flex items-center gap-1.5 text-sm font-medium text-neutral-900 underline-offset-4 hover:underline"
            >
              Upload a video <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}

        {/* Grid */}
        {!loading && videos.length > 0 && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {videos.map((v) => (
              <VideoCard
                key={v.videoId}
                video={v}
                offerCount={offerCounts[v.videoId]}
                streamUrl={streamUrls[v.videoId]}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
