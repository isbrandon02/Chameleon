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
  return (
    <Link to={`/videos/${video.videoId}`}>
      <div className="group cursor-pointer">
        {/* Portrait thumbnail — 9:16 */}
        <div className="relative w-full overflow-hidden rounded-xl bg-neutral-100" style={{ aspectRatio: "9/16" }}>
          {streamUrl ? (
            <video
              src={streamUrl}
              preload="metadata"
              muted
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              <Play className="h-8 w-8 text-neutral-300" />
            </div>
          )}

          {/* Offer badge */}
          {offerCount !== undefined && offerCount > 0 && (
            <span className="absolute right-2 top-2 rounded-full bg-violet-600 px-2 py-0.5 text-xs font-medium text-white">
              {offerCount} offer{offerCount !== 1 ? "s" : ""}
            </span>
          )}

          {/* Bottom gradient overlay */}
          <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-black/50 to-transparent" />

          {/* Status dot */}
          <span className={`absolute bottom-3 right-3 h-2 w-2 rounded-full ${statusDot[video.status]}`} />
        </div>

        {/* Title below */}
        <div className="mt-2 px-0.5">
          <p className="line-clamp-2 text-sm font-medium leading-snug text-neutral-900">
            {video.title}
          </p>
          <p className="mt-0.5 text-xs text-neutral-400">
            {new Date(video.createdAt).toLocaleDateString()}
          </p>
        </div>
      </div>
    </Link>
  );
}
