import { useAuth0 } from "@auth0/auth0-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
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
      // 1. Get pre-signed URL from FastAPI
      const { uploadUrl, videoId } = await getUploadUrl(getAccessTokenSilently, {
        fileName: file.name,
        contentType: file.type,
      });

      // 2. Upload directly to S3 with progress tracking
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
            : reject(new Error(`S3 upload failed: ${xhr.status}`));
        xhr.onerror = () => reject(new Error("Network error during upload"));
        xhr.send(file);
      });

      // 3. Register video metadata in DynamoDB via FastAPI
      const s3Location = uploadUrl.split("?")[0]; // strip query params
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
    <div className="min-h-screen">
      <Navbar />
      <main className="mx-auto max-w-2xl px-6 py-10">
        <h1 className="mb-6 text-2xl font-bold">Upload a Video</h1>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-1.5">
            <Label htmlFor="title">Title *</Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="My awesome video"
              required
              disabled={uploading}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Tell brands what your video is about…"
              rows={4}
              disabled={uploading}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="file">Video file *</Label>
            <Input
              id="file"
              type="file"
              ref={fileRef}
              accept="video/*"
              required
              disabled={uploading}
            />
          </div>

          {uploading && (
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">
                Uploading… {progress}%
              </p>
              <Progress value={progress} />
            </div>
          )}

          <Button type="submit" disabled={uploading} className="w-full">
            {uploading ? "Uploading…" : "Upload Video"}
          </Button>
        </form>
      </main>
    </div>
  );
}
