import { useAuth0 } from "@auth0/auth0-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Navbar from "@/components/Navbar";
import VideoCard from "@/components/VideoCard";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getCreatorVideos, getVideoOffers, type VideoRecord } from "@/lib/api";

export default function CreatorDashboard() {
  const { user, getAccessTokenSilently } = useAuth0();
  const [videos, setVideos] = useState<VideoRecord[]>([]);
  const [offerCounts, setOfferCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const creatorId = user?.sub ?? "";

  useEffect(() => {
    if (!creatorId) return;

    (async () => {
      try {
        const vids = await getCreatorVideos(getAccessTokenSilently, creatorId);
        setVideos(vids);

        // Fetch pending offer counts in parallel
        const counts = await Promise.all(
          vids.map(async (v) => {
            try {
              const offers = await getVideoOffers(
                getAccessTokenSilently,
                v.videoId
              );
              return {
                id: v.videoId,
                count: offers.filter((o) => o.status === "pending").length,
              };
            } catch {
              return { id: v.videoId, count: 0 };
            }
          })
        );
        setOfferCounts(
          Object.fromEntries(counts.map(({ id, count }) => [id, count]))
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load videos");
      } finally {
        setLoading(false);
      }
    })();
  }, [creatorId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold">My Videos</h1>
          <Link to="/upload">
            <Button>Upload Video</Button>
          </Link>
        </div>

        {loading && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-48 rounded-lg" />
            ))}
          </div>
        )}

        {error && (
          <p className="text-destructive">{error}</p>
        )}

        {!loading && !error && videos.length === 0 && (
          <div className="py-20 text-center text-muted-foreground">
            <p className="mb-4">No videos yet.</p>
            <Link to="/upload">
              <Button variant="outline">Upload your first video</Button>
            </Link>
          </div>
        )}

        {!loading && videos.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {videos.map((v) => (
              <VideoCard
                key={v.videoId}
                video={v}
                offerCount={offerCounts[v.videoId]}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
