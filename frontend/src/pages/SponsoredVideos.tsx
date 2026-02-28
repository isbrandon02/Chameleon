import { useAuth0 } from "@auth0/auth0-react";
import { useEffect, useState } from "react";
import { Clapperboard, Loader2 } from "lucide-react";
import PageShell from "@/components/PageShell";
import {
  getAcceptedOffers,
  getEditedStreamUrl,
  getVideo,
  type Offer,
  type VideoRecord,
} from "@/lib/api";

const ROLES_CLAIM = "https://chameleon.com/roles";

interface EnrichedOffer extends Offer {
  videoTitle?: string;
  streamUrl?: string;
  loadingStream?: boolean;
}

function EditStatusBadge({ editStatus }: { editStatus?: string }) {
  if (!editStatus) {
    return (
      <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] font-medium text-white/70">
        Queued
      </span>
    );
  }
  if (editStatus === "editing") {
    return (
      <span className="flex items-center gap-1.5 rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] font-medium text-white/70">
        <Loader2 className="h-3 w-3 animate-spin" />
        Processing
      </span>
    );
  }
  if (editStatus === "complete") {
    return (
      <span className="rounded-full bg-[#4ADE80]/10 px-2.5 py-1 text-[11px] font-medium text-[#4ADE80]">
        Ready
      </span>
    );
  }
  return (
    <span className="rounded-full bg-red-500/10 px-2.5 py-1 text-[11px] font-medium text-red-400">
      Error
    </span>
  );
}

export default function SponsoredVideos() {
  const { user, getAccessTokenSilently } = useAuth0();
  const [offers, setOffers] = useState<EnrichedOffer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const roles = ((user?.[ROLES_CLAIM] as string[] | undefined) ?? []).map(
    (r) => r.toLowerCase()
  );
  const isCreator = roles.includes("creator");

  useEffect(() => {
    (async () => {
      try {
        const accepted = await getAcceptedOffers(getAccessTokenSilently);

        const uniqueVideoIds = [...new Set(accepted.map((o) => o.videoId))];
        const videoMap: Record<string, VideoRecord> = {};
        await Promise.all(
          uniqueVideoIds.map(async (vid) => {
            try {
              videoMap[vid] = await getVideo(getAccessTokenSilently, vid);
            } catch {
              // title falls back to videoId
            }
          })
        );

        setOffers(
          accepted.map((o) => ({
            ...o,
            videoTitle: videoMap[o.videoId]?.title,
          }))
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadStream(offerId: string) {
    setOffers((prev) =>
      prev.map((o) =>
        o.offerId === offerId ? { ...o, loadingStream: true } : o
      )
    );
    try {
      const { streamUrl } = await getEditedStreamUrl(
        getAccessTokenSilently,
        offerId
      );
      setOffers((prev) =>
        prev.map((o) =>
          o.offerId === offerId
            ? { ...o, streamUrl, loadingStream: false }
            : o
        )
      );
    } catch {
      setOffers((prev) =>
        prev.map((o) =>
          o.offerId === offerId ? { ...o, loadingStream: false } : o
        )
      );
    }
  }

  return (
    <PageShell>
      <div className="mx-auto max-w-6xl px-6 pb-20 pt-10 sm:px-10">
        <div className="mb-10">
          <h1 className="text-[28px] font-semibold tracking-tight">
            Sponsored Videos
          </h1>
          <p className="mt-2 text-[14px] text-white/70">
            {isCreator
              ? "Videos where you accepted a sponsorship deal — edited versions appear here."
              : "Videos you sponsored — edited versions appear here after the creator accepts."}
          </p>
        </div>

        {loading && (
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-36 w-full animate-pulse rounded-2xl bg-white/[0.04]"
              />
            ))}
          </div>
        )}

        {error && <p className="text-[14px] text-red-400">{error}</p>}

        {!loading && !error && offers.length === 0 && (
          <div className="flex flex-col items-center py-28 text-center">
            <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-white/[0.06] bg-white/[0.03]">
              <Clapperboard className="h-6 w-6 text-white/70" />
            </div>
            <p className="text-[15px] font-medium text-white/70">
              No sponsored videos yet
            </p>
            <p className="mt-1.5 text-[14px] text-white/70">
              {isCreator
                ? "Accept a sponsorship offer on one of your videos to see the edited version here."
                : "Make an offer on a video and wait for the creator to accept."}
            </p>
          </div>
        )}

        {!loading && offers.length > 0 && (
          <div className="space-y-4">
            {offers.map((offer) => (
              <div
                key={offer.offerId}
                className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-6"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[15px] font-medium text-white">
                      {offer.videoTitle ?? offer.videoId}
                    </p>
                    <p className="mt-1 text-[13px] text-white/70">
                      ${Number(offer.proposedBudget).toLocaleString()} deal
                      {offer.message && <> · {offer.message}</>}
                    </p>
                    <p className="mt-0.5 text-[12px] text-white/70">
                      {isCreator
                        ? `Sponsor: ${offer.companyName || offer.companyId}`
                        : `Creator: ${offer.creatorName || offer.creatorId}`}
                    </p>
                  </div>
                  <div className="shrink-0 pt-0.5">
                    <EditStatusBadge editStatus={offer.editStatus} />
                  </div>
                </div>

                <div className="mt-5">
                  {offer.editStatus === "complete" && (
                    <>
                      {offer.streamUrl ? (
                        <video
                          src={offer.streamUrl}
                          controls
                          className="w-full rounded-xl bg-black"
                          style={{ maxHeight: 480 }}
                        />
                      ) : (
                        <button
                          className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.04] px-4 py-2 text-[13px] font-medium text-white/70 transition-colors hover:bg-white/[0.07] hover:text-white disabled:opacity-50"
                          disabled={offer.loadingStream}
                          onClick={() => loadStream(offer.offerId)}
                        >
                          {offer.loadingStream ? (
                            <>
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              Loading…
                            </>
                          ) : (
                            "Watch Edited Video"
                          )}
                        </button>
                      )}
                    </>
                  )}

                  {offer.editStatus === "editing" && (
                    <p className="text-[13px] text-white/70">
                      The edited video is being generated — check back in a minute.
                    </p>
                  )}

                  {offer.editStatus === "error" && (
                    <p className="text-[13px] text-red-400">
                      Video editing failed. Please contact support.
                    </p>
                  )}

                  {!offer.editStatus && (
                    <p className="text-[13px] text-white/70">
                      Video editing will start shortly.
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </PageShell>
  );
}
