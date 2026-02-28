import { useAuth0 } from "@auth0/auth0-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import Navbar from "@/components/Navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  createOffer,
  getVideo,
  getVideoOffers,
  updateOfferStatus,
  type Offer,
  type VideoRecord,
} from "@/lib/api";

const ROLES_CLAIM = "https://chameleon.com/roles";

export default function VideoDetail() {
  const { videoId } = useParams<{ videoId: string }>();
  const { user, getAccessTokenSilently } = useAuth0();

  const [video, setVideo] = useState<VideoRecord | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [offerBudget, setOfferBudget] = useState("");
  const [offerMessage, setOfferMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  const roles = ((user?.[ROLES_CLAIM] as string[] | undefined) ?? []).map((r) =>
    r.toLowerCase()
  );
  const isCompany = roles.includes("company");
  const isCreator = roles.includes("creator");

  async function loadData() {
    if (!videoId) return;
    try {
      const [vid, offs] = await Promise.all([
        getVideo(getAccessTokenSilently, videoId),
        getVideoOffers(getAccessTokenSilently, videoId),
      ]);
      setVideo(vid);
      setOffers(offs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [videoId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleMakeOffer(e: React.FormEvent) {
    e.preventDefault();
    if (!videoId) return;
    setSubmitting(true);
    try {
      await createOffer(getAccessTokenSilently, {
        videoId,
        proposedBudget: parseFloat(offerBudget),
        message: offerMessage.trim() || undefined,
      });
      toast.success("Offer submitted!");
      setDialogOpen(false);
      setOfferBudget("");
      setOfferMessage("");
      await loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to submit offer");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleOfferAction(
    offerId: string,
    status: "accepted" | "rejected"
  ) {
    try {
      await updateOfferStatus(getAccessTokenSilently, offerId, status);
      toast.success(`Offer ${status}`);
      await loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update offer");
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <main className="mx-auto max-w-4xl px-6 py-8">
          <Skeleton className="mb-4 h-8 w-2/3" />
          <Skeleton className="mb-2 h-4 w-full" />
          <Skeleton className="h-48 w-full rounded-lg" />
        </main>
      </div>
    );
  }

  if (error || !video) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <main className="mx-auto max-w-4xl px-6 py-8">
          <p className="text-destructive">{error ?? "Video not found"}</p>
        </main>
      </div>
    );
  }

  const report = video.analysisReport;

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="mx-auto max-w-4xl px-6 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">{video.title}</h1>
            {video.description && (
              <p className="mt-1 text-muted-foreground">{video.description}</p>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              {new Date(video.createdAt).toLocaleDateString()} ·{" "}
              <Badge variant="outline">{video.status}</Badge>
            </p>
          </div>

          {isCompany && video.status === "analyzed" && (
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button>Make Offer</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Submit Sponsorship Offer</DialogTitle>
                </DialogHeader>
                <form onSubmit={handleMakeOffer} className="space-y-4 pt-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="budget">Proposed Budget (USD) *</Label>
                    <Input
                      id="budget"
                      type="number"
                      min="1"
                      step="0.01"
                      value={offerBudget}
                      onChange={(e) => setOfferBudget(e.target.value)}
                      placeholder="500"
                      required
                      disabled={submitting}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="msg">Message</Label>
                    <Textarea
                      id="msg"
                      value={offerMessage}
                      onChange={(e) => setOfferMessage(e.target.value)}
                      placeholder="Tell the creator about your brand…"
                      rows={3}
                      disabled={submitting}
                    />
                  </div>
                  <Button type="submit" className="w-full" disabled={submitting}>
                    {submitting ? "Submitting…" : "Submit Offer"}
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          )}
        </div>

        {/* Analysis Report */}
        {report && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">AI Analysis</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {report.summary && (
                <p className="text-sm">{report.summary}</p>
              )}
              {report.topics && report.topics.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground uppercase">
                    Topics
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {report.topics.map((t) => (
                      <Badge key={t} variant="secondary">
                        {t}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {report.hashtags && report.hashtags.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground uppercase">
                    Hashtags
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {report.hashtags.map((h) => (
                      <span key={h} className="text-sm text-muted-foreground">
                        #{h}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {report.sentiment && (
                <p className="text-sm">
                  <span className="font-medium">Sentiment:</span>{" "}
                  {report.sentiment}
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Offers table — visible to creator */}
        {isCreator && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Sponsorship Offers</CardTitle>
            </CardHeader>
            <CardContent>
              {offers.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No offers yet. Share your video to attract brands.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Company</TableHead>
                      <TableHead>Budget</TableHead>
                      <TableHead>Message</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {offers.map((o) => (
                      <TableRow key={o.offerId}>
                        <TableCell className="text-sm">{o.companyId}</TableCell>
                        <TableCell className="text-sm">
                          ${o.proposedBudget.toLocaleString()}
                        </TableCell>
                        <TableCell className="max-w-xs truncate text-sm text-muted-foreground">
                          {o.message ?? "—"}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              o.status === "accepted"
                                ? "default"
                                : o.status === "rejected"
                                  ? "destructive"
                                  : "secondary"
                            }
                          >
                            {o.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {o.status === "pending" && (
                            <div className="flex gap-2">
                              <Button
                                size="sm"
                                onClick={() =>
                                  handleOfferAction(o.offerId, "accepted")
                                }
                              >
                                Accept
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() =>
                                  handleOfferAction(o.offerId, "rejected")
                                }
                              >
                                Reject
                              </Button>
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
