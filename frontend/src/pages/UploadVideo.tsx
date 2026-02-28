import { useAuth0 } from "@auth0/auth0-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Upload } from "lucide-react";
import { toast } from "sonner";
import PageShell from "@/components/PageShell";
import { getUploadUrl, registerVideo } from "@/lib/api";

export default function UploadVideo() {
  const { getAccessTokenSilently } = useAuth0();
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file || !title.trim()) return;

    setUploading(true);
    setProgress(0);

    try {
      const { uploadUrl, videoId } = await getUploadUrl(getAccessTokenSilently, {
        fileName: file.name,
        contentType: file.type,
      });

      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("PUT", uploadUrl);
        xhr.setRequestHeader("Content-Type", file.type);
        xhr.upload.onprogress = (evt) => {
          if (evt.lengthComputable) {
            setProgress(Math.round((evt.loaded / evt.total) * 100));
          }
        };
        xhr.onload = () =>
          xhr.status >= 200 && xhr.status < 300
            ? resolve()
            : reject(new Error(`Upload failed: ${xhr.status}`));
        xhr.onerror = () => reject(new Error("Network error"));
        xhr.send(file);
      });

      const s3Location = uploadUrl.split("?")[0];
      await registerVideo(getAccessTokenSilently, {
        videoId,
        title: title.trim(),
        description: description.trim() || undefined,
        s3Location,
      });

      toast.success("Video uploaded! Analysis will begin shortly.");
      navigate("/dashboard");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      toast.error(msg);
    } finally {
      setUploading(false);
    }
  }

  return (
    <PageShell>
      <div className="mx-auto max-w-xl px-6 pb-20 pt-10 sm:px-10">
        <h1 className="mb-8 text-[28px] font-semibold tracking-tight">Upload a Video</h1>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label htmlFor="title" className="mb-2 block text-[13px] font-medium text-white/50">
              Title
            </label>
            <input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="My awesome video"
              required
              disabled={uploading}
              className="w-full rounded-xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 text-[14px] text-white placeholder-white/20 outline-none transition-colors focus:border-[#4ADE80]/30 disabled:opacity-50"
            />
          </div>

          <div>
            <label htmlFor="description" className="mb-2 block text-[13px] font-medium text-white/50">
              Description
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Tell brands what your video is about"
              rows={4}
              disabled={uploading}
              className="w-full resize-none rounded-xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 text-[14px] text-white placeholder-white/20 outline-none transition-colors focus:border-[#4ADE80]/30 disabled:opacity-50"
            />
          </div>

          <div>
            <label htmlFor="file" className="mb-2 block text-[13px] font-medium text-white/50">
              Video file
            </label>
            <input
              id="file"
              type="file"
              ref={fileRef}
              accept="video/*"
              required
              disabled={uploading}
              className="w-full rounded-xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 text-[14px] text-white/50 file:mr-3 file:rounded-full file:border-0 file:bg-white/[0.06] file:px-3 file:py-1 file:text-[12px] file:font-medium file:text-white/60 disabled:opacity-50"
            />
          </div>

          {uploading && (
            <div>
              <div className="mb-2 flex items-center justify-between text-[13px]">
                <span className="text-white/40">Uploading</span>
                <span className="font-medium text-[#4ADE80]">{progress}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
                <div
                  className="h-full rounded-full bg-[#4ADE80] transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={uploading}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#4ADE80] py-3 text-[14px] font-semibold text-[#0B0F0E] transition-all hover:brightness-110 disabled:opacity-50"
          >
            <Upload className="h-4 w-4" />
            {uploading ? "Uploading..." : "Upload Video"}
          </button>
        </form>
      </div>
    </PageShell>
  );
}
