import { useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { FeedCard } from "../components/FeedCard";
import { ContextRail } from "../components/ContextRail";
import { MorningBrief } from "../components/MorningBrief";
import { ItemDrawer } from "../components/ItemDrawer";
import type { FeedItem } from "../types/api";

const WINDOW_OPTIONS = ["6h", "12h", "24h", "48h", "7d"];

export function FeedPage() {
  const [searchParams] = useSearchParams();
  const activeUser = searchParams.get("user") ?? "";
  const [eventsOnly, setEventsOnly] = useState(true);
  const [window, setWindow] = useState("24h");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, isError } =
    useInfiniteQuery({
      queryKey: ["feed", eventsOnly, window, activeUser],
      queryFn: ({ pageParam }) =>
        api.feed({
          events_only: eventsOnly || undefined,
          window,
          limit: 20,
          cursor: pageParam as string | undefined,
          user: activeUser || undefined,
        }),
      initialPageParam: undefined as string | undefined,
      getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined,
      staleTime: 30_000,
    });

  const allItems = data?.pages.flatMap((p) => p.items) ?? [];
  const context = data?.pages[0]?.context;
  const topEvents = context?.top_events ?? [];

  return (
    <div className="flex gap-6 min-h-0">
      <div className="flex-1 min-w-0">
        <MorningBrief events={topEvents} />

        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <button
            onClick={() => setEventsOnly(!eventsOnly)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              eventsOnly
                ? "bg-brand-500 text-slate-950 border-brand-500"
                : "border-surface-border text-slate-400 hover:border-slate-500"
            }`}
          >
            {eventsOnly ? "Signal articles" : "All articles"}
          </button>
          <div className="flex items-center gap-1">
            {WINDOW_OPTIONS.map((w) => (
              <button
                key={w}
                onClick={() => setWindow(w)}
                className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                  window === w
                    ? "bg-slate-700 text-white border-slate-700"
                    : "border-surface-border text-slate-400 hover:border-slate-500"
                }`}
              >
                {w}
              </button>
            ))}
          </div>
        </div>

        {/* Feed list */}
        {isLoading && (
          <div className="space-y-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-28 bg-slate-800 rounded-lg animate-pulse" />
            ))}
          </div>
        )}

        {isError && (
          <div className="text-sm text-red-400 bg-red-500/10 px-4 py-3 rounded-lg">
            Failed to load feed. Check that the API is running on port 8001.
          </div>
        )}

        {!isLoading && allItems.length === 0 && (
          <div className="text-sm text-slate-500 text-center py-12">
            No articles match the current filters.
          </div>
        )}

        <div className="space-y-2">
          {allItems.map((item) => (
            <FeedCard key={item.id} item={item} onClick={(i: FeedItem) => setSelectedId(i.id)} />
          ))}
        </div>

        {hasNextPage && (
          <div className="mt-4 flex justify-center">
            <button
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
              className="text-sm text-brand-400 hover:text-brand-300 disabled:text-slate-500 px-4 py-2 border border-surface-border rounded-lg hover:border-brand-500/30 transition-colors"
            >
              {isFetchingNextPage ? "Loading..." : "Load more"}
            </button>
          </div>
        )}
      </div>

      <ContextRail context={context} />

      <ItemDrawer itemId={selectedId} onClose={() => setSelectedId(null)} />
    </div>
  );
}
