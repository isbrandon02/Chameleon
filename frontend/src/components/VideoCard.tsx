import { Link } from "react-router-dom";
import type { VideoRecord } from "@/lib/api";

const statusDot: Record<VideoRecord["status"], string> = {
  uploaded: "bg-yellow-400",
  analyzing: "bg-blue-400",
  analyzed: "bg-emerald-400",
};

const thumbnailGradient = [
  "from-violet-100 to-indigo-100",
  "from-sky-100 to-cyan-100",
  "from-rose-100 to-pink-100",
  "from-amber-100 to-yellow-100",
  "from-emerald-100 to-teal-100",
];

function pickGradient(id: string) {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = id.charCodeAt(i) + ((hash << 5) - hash);
  return thumbnailGradient[Math.abs(hash) % thumbnailGradient.length];
}

interface Props {
  video: VideoRecord;
  offerCount?: number;
}

export default function VideoCard({ video, offerCount }: Props) {
  const topics = video.analysisReport?.topics ?? [];

  return (
    <Link to={`/videos/${video.videoId}`}>
      <div className="group rounded-xl border border-neutral-100 bg-white transition-shadow hover:shadow-md">
        {/* Thumbnail */}
        <div className={`h-36 rounded-t-xl bg-gradient-to-br ${pickGradient(video.videoId)}`} />

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
