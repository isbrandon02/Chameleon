import { Play } from "lucide-react";
import { Link } from "react-router-dom";
import type { VideoRecord } from "@/lib/api";

const statusColor: Record<VideoRecord["status"], string> = {
  uploaded: "bg-amber-400",
  analyzing: "bg-blue-400",
  analyzed: "bg-[#4ADE80]",
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
        <div
          className="relative w-full overflow-hidden rounded-2xl border border-white/[0.04] bg-white/[0.03]"
          style={{ aspectRatio: "9/16" }}
        >
          {streamUrl ? (
            <video
              src={streamUrl}
              preload="metadata"
              muted
              className="h-full w-full object-cover transition-transform duration-500 ease-out group-hover:scale-105"
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              <Play className="h-8 w-8 text-white/10" />
            </div>
          )}

          {offerCount !== undefined && offerCount > 0 && (
            <span className="absolute right-2.5 top-2.5 rounded-full bg-[#4ADE80] px-2.5 py-0.5 text-[11px] font-semibold text-[#0B0F0E]">
              {offerCount} offer{offerCount !== 1 ? "s" : ""}
            </span>
          )}

          <div className="absolute bottom-0 left-0 right-0 h-20 bg-gradient-to-t from-[#0B0F0E]/80 to-transparent" />

          <span
            className={`absolute bottom-3 right-3 h-2 w-2 rounded-full ${statusColor[video.status]}`}
          />
        </div>

        <div className="mt-3 px-0.5">
          <p className="line-clamp-2 text-[14px] font-medium leading-snug text-white/80">
            {video.title}
          </p>
          <p className="mt-1 text-[12px] text-white/25">
            {new Date(video.createdAt).toLocaleDateString()}
          </p>
        </div>
      </div>
    </Link>
  );
}
