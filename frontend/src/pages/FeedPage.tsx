import { useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { FeedCard } from "../components/FeedCard";
import { ContextRail } from "../components/ContextRail";
import { ItemDrawer } from "../components/ItemDrawer";
import type { FeedItem } from "../types/api";

const RELEVANCE_OPTIONS = [
  { value: 1, label: "All" },
  { value: 3, label: "3+" },
  { value: 4, label: "4+" },
  { value: 5, label: "5 only" },
];

const WINDOW_OPTIONS = ["6h", "12h", "24h", "48h", "7d"];

export function FeedPage() {
  const [searchParams] = useSearchParams();
  const activeUser = searchParams.get("user") ?? "";
  const [minRelevance, setMinRelevance] = useState(2);
  const [window, setWindow] = useState("24h");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, isError } =
    useInfiniteQuery({
      queryKey: ["feed", minRelevance, window, activeUser],
      queryFn: ({ pageParam }) =>
        api.feed({
          min_relevance: minRelevance,
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

  return (
    <div className="flex gap-6 min-h-0">
      <div className="flex-1 min-w-0">
        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="flex items-center gap-1">
            {RELEVANCE_OPTIONS.map((o) => (
              <button
                key={o.value}
                onClick={() => setMinRelevance(o.value)}
                className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                  minRelevance === o.value
                    ? "bg-brand-600 text-white border-brand-600"
                    : "border-gray-300 text-gray-600 hover:border-brand-400"
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            {WINDOW_OPTIONS.map((w) => (
              <button
                key={w}
                onClick={() => setWindow(w)}
                className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                  window === w
                    ? "bg-gray-700 text-white border-gray-700"
                    : "border-gray-300 text-gray-600 hover:border-gray-400"
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
              <div key={i} className="h-28 bg-gray-100 rounded-lg animate-pulse" />
            ))}
          </div>
        )}

        {isError && (
          <div className="text-sm text-red-500 bg-red-50 px-4 py-3 rounded-lg">
            Failed to load feed. Check that the API is running on port 8001.
          </div>
        )}

        {!isLoading && allItems.length === 0 && (
          <div className="text-sm text-gray-400 text-center py-12">
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
              className="text-sm text-brand-600 hover:text-brand-700 disabled:text-gray-400 px-4 py-2 border border-brand-300 rounded-md hover:bg-brand-50 transition-colors"
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
