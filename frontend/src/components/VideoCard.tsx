import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { VideoRecord } from "@/lib/api";

const statusColors: Record<VideoRecord["status"], string> = {
  uploaded: "bg-yellow-100 text-yellow-800",
  analyzing: "bg-blue-100 text-blue-800",
  analyzed: "bg-green-100 text-green-800",
};

interface Props {
  video: VideoRecord;
  offerCount?: number;
}

export default function VideoCard({ video, offerCount }: Props) {
  const topics = video.analysisReport?.topics ?? [];
  const hashtags = video.analysisReport?.hashtags ?? [];

  return (
    <Link to={`/videos/${video.videoId}`}>
      <Card className="cursor-pointer transition-shadow hover:shadow-md">
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="line-clamp-2 text-base">{video.title}</CardTitle>
            <Badge className={statusColors[video.status]}>{video.status}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {video.description && (
            <p className="mb-3 line-clamp-2 text-sm text-muted-foreground">
              {video.description}
            </p>
          )}

          {topics.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1">
              {topics.slice(0, 4).map((t) => (
                <Badge key={t} variant="secondary" className="text-xs">
                  {t}
                </Badge>
              ))}
            </div>
          )}

          {hashtags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {hashtags.slice(0, 4).map((h) => (
                <span key={h} className="text-xs text-muted-foreground">
                  #{h}
                </span>
              ))}
            </div>
          )}

          {offerCount !== undefined && offerCount > 0 && (
            <p className="mt-3 text-xs font-medium text-primary">
              {offerCount} pending offer{offerCount !== 1 ? "s" : ""}
            </p>
          )}

          <p className="mt-2 text-xs text-muted-foreground">
            {new Date(video.createdAt).toLocaleDateString()}
          </p>
        </CardContent>
      </Card>
    </Link>
  );
}
