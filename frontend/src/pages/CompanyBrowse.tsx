import { useAuth0 } from "@auth0/auth0-react";
import { useEffect, useState } from "react";
import PageShell from "@/components/PageShell";
import VideoCard from "@/components/VideoCard";
import { listVideos, getStreamUrl, type VideoRecord } from "@/lib/api";

export default function CompanyBrowse() {
  const { getAccessTokenSilently } = useAuth0();
  const [videos, setVideos] = useState<VideoRecord[]>([]);
  const [streamUrls, setStreamUrls] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const vids = await listVideos(getAccessTokenSilently);
        setVideos(vids);

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
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <PageShell>
      <div className="mx-auto max-w-6xl px-6 pb-20 pt-10 sm:px-10">
        <div className="mb-10">
          <h1 className="text-[28px] font-semibold tracking-tight">Browse Videos</h1>
          <p className="mt-2 text-[14px] text-white/30">
            Discover content available for brand integration.
          </p>
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
            <p className="text-[15px] font-medium text-white/70">No videos yet</p>
            <p className="mt-1.5 text-[14px] text-white/30">
              Check back soon for new content.
            </p>
          </div>
        )}

        {!loading && videos.length > 0 && (
          <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-4">
            {videos.map((v) => (
              <VideoCard key={v.videoId} video={v} streamUrl={streamUrls[v.videoId]} />
            ))}
          </div>
        )}
      </div>
    </PageShell>
  );
}
