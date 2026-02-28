import { useState } from "react";
import { Check, Pencil, Play, Trash2, X } from "lucide-react";
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
  onTitleChange?: (videoId: string, newTitle: string) => void;
  onDelete?: (videoId: string) => void;
}

export default function VideoCard({
  video,
  offerCount,
  streamUrl,
  onTitleChange,
  onDelete,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(video.title);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const hasActions = !!(onTitleChange || onDelete);

  async function handleSave() {
    const trimmed = draftTitle.trim();
    if (!trimmed || trimmed === video.title) {
      setEditing(false);
      setDraftTitle(video.title);
      return;
    }
    setSaving(true);
    try {
      await onTitleChange?.(video.videoId, trimmed);
    } finally {
      setSaving(false);
      setEditing(false);
    }
  }

  function handleCancel() {
    setDraftTitle(video.title);
    setEditing(false);
  }

  return (
    <div className="group">
      <Link to={`/videos/${video.videoId}`}>
        <div
          className="relative w-full cursor-pointer overflow-hidden rounded-2xl border border-white/[0.04] bg-white/[0.03]"
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
              <Play className="h-8 w-8 text-white/70" />
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
      </Link>

      <div className="mt-3 px-0.5">
        {editing ? (
          <div className="flex items-center gap-1.5">
            <input
              className="min-w-0 flex-1 rounded-lg border border-white/[0.10] bg-white/[0.06] px-2 py-1 text-[13px] text-white outline-none focus:border-[#4ADE80]/40"
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSave();
                if (e.key === "Escape") handleCancel();
              }}
              autoFocus
              disabled={saving}
            />
            <button
              onClick={handleSave}
              disabled={saving}
              className="shrink-0 transition-colors hover:text-[#4ADE80]"
            >
              <Check className="h-3.5 w-3.5 text-[#4ADE80]" />
            </button>
            <button
              onClick={handleCancel}
              disabled={saving}
              className="shrink-0 transition-colors"
            >
              <X className="h-3.5 w-3.5 text-white/70 hover:text-white/60" />
            </button>
          </div>
        ) : (
          <div className="flex items-start justify-between gap-1">
            <p className="line-clamp-2 text-[14px] font-medium leading-snug text-white/80">
              {video.title}
            </p>

            {hasActions && (
              <div className="flex shrink-0 items-center gap-1 pt-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                {onTitleChange && (
                  <button
                    onClick={() => setEditing(true)}
                    className="transition-colors"
                    title="Rename"
                  >
                    <Pencil className="h-3.5 w-3.5 text-white/70 hover:text-white/70" />
                  </button>
                )}

                {onDelete && !confirmDelete && (
                  <button
                    onClick={() => setConfirmDelete(true)}
                    className="transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="h-3.5 w-3.5 text-white/70 hover:text-red-400" />
                  </button>
                )}

                {onDelete && confirmDelete && (
                  <>
                    <button
                      onClick={() => onDelete(video.videoId)}
                      className="text-[11px] font-medium text-red-400 transition-colors hover:text-red-300"
                    >
                      Delete?
                    </button>
                    <button
                      onClick={() => setConfirmDelete(false)}
                      className="transition-colors"
                    >
                      <X className="h-3 w-3 text-white/70 hover:text-white/60" />
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        )}

        <p className="mt-1 text-[12px] text-white/70">
          {new Date(video.createdAt).toLocaleDateString()}
        </p>
      </div>
    </div>
  );
}
