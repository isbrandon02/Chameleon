import { useAuth0 } from "@auth0/auth0-react";
import { useEffect, useState } from "react";
import Navbar from "@/components/Navbar";
import VideoCard from "@/components/VideoCard";
import { Skeleton } from "@/components/ui/skeleton";
import { listVideos, type VideoRecord } from "@/lib/api";

export default function CompanyBrowse() {
  const { getAccessTokenSilently } = useAuth0();
  const [videos, setVideos] = useState<VideoRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listVideos(getAccessTokenSilently)
      .then(setVideos)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load videos")
      )
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold">Browse Videos</h1>
          <p className="mt-1 text-muted-foreground">
            Videos available for sponsorship
          </p>
        </div>

        {loading && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 9 }).map((_, i) => (
              <Skeleton key={i} className="h-48 rounded-lg" />
            ))}
          </div>
        )}

        {error && <p className="text-destructive">{error}</p>}

        {!loading && !error && videos.length === 0 && (
          <div className="py-20 text-center text-muted-foreground">
            No analyzed videos available yet. Check back soon.
          </div>
        )}

        {!loading && videos.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {videos.map((v) => (
              <VideoCard key={v.videoId} video={v} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
