import { Play } from "lucide-react";
import { Link } from "react-router-dom";
import type { VideoRecord } from "@/lib/api";

const statusDot: Record<VideoRecord["status"], string> = {
  uploaded: "bg-yellow-400",
  analyzing: "bg-blue-400",
  analyzed: "bg-emerald-400",
};

interface Props {
  video: VideoRecord;
  offerCount?: number;
  streamUrl?: string;
}

export default function VideoCard({ video, offerCount, streamUrl }: Props) {
  const topics = video.analysisReport?.topics ?? [];

  return (
    <Link to={`/videos/${video.videoId}`}>
      <div className="group rounded-xl border border-neutral-100 bg-white transition-shadow hover:shadow-md">
        {/* Thumbnail */}
        <div className="relative h-36 overflow-hidden rounded-t-xl bg-neutral-100">
          {streamUrl ? (
            <video
              src={streamUrl}
              preload="metadata"
              muted
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              <Play className="h-7 w-7 text-neutral-300" />
            </div>
          )}
        </div>

        {/* Content */}
        <div className="p-4">
          <div className="mb-1 flex items-center justify-between gap-2">
            <p className="line-clamp-1 text-sm font-medium text-neutral-900">
              {video.title}
            </p>
            <span className={`h-2 w-2 shrink-0 rounded-full ${statusDot[video.status]}`} />
          </div>

          {video.description && (
            <p className="mb-3 line-clamp-2 text-xs leading-relaxed text-neutral-400">
              {video.description}
            </p>
          )}

          {topics.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-1">
              {topics.slice(0, 3).map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-500"
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between">
            <span className="text-xs text-neutral-300">
              {new Date(video.createdAt).toLocaleDateString()}
            </span>
            {offerCount !== undefined && offerCount > 0 && (
              <span className="text-xs font-medium text-violet-600">
                {offerCount} offer{offerCount !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}
