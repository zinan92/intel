import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function EventHistoryPage() {
  const [tagFilter, setTagFilter] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["event-history"],
    queryFn: () => api.eventHistory({ days: 30, limit: 100 }),
    staleTime: 60_000,
  });

  const filtered = useMemo(() => {
    const events = data?.events ?? [];
    if (!tagFilter.trim()) return events;
    const q = tagFilter.toLowerCase();
    return events.filter((e) => e.narrative_tag.includes(q));
  }, [data, tagFilter]);

  return (
    <div className="max-w-2xl">
      <h2 className="text-lg font-semibold text-gray-800 mb-1">Event History</h2>
      <p className="text-sm text-gray-500 mb-4">Last 30 days · {filtered.length} events</p>
      <input
        type="text"
        placeholder="Filter by topic..."
        value={tagFilter}
        onChange={(e) => setTagFilter(e.target.value)}
        className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 mb-4 focus:outline-none focus:border-brand-400"
      />
      {isLoading && (
        <div className="space-y-3 animate-pulse">
          {[...Array(5)].map((_, i) => <div key={i} className="h-16 bg-gray-100 rounded-lg" />)}
        </div>
      )}
      <div className="space-y-2">
        {filtered.map((event) => (
          <Link
            key={event.id}
            to={`/events/${event.id}`}
            className="block border border-gray-200 rounded-lg p-3 hover:border-brand-400 hover:shadow-sm transition-all"
          >
            <div className="flex justify-between items-start">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">{formatDate(event.window_start)}</span>
                  <span className="text-sm font-semibold text-gray-800 truncate">
                    {event.narrative_tag.replace(/-/g, " ")}
                  </span>
                </div>
                {event.narrative_summary && (
                  <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{event.narrative_summary}</p>
                )}
                <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                  <span>{event.source_count} sources · {event.article_count} articles</span>
                  {event.tickers.length > 0 && (
                    <span>{event.tickers.slice(0, 3).map(t => `$${t}`).join(" ")}</span>
                  )}
                </div>
              </div>
              <div className="text-right shrink-0 ml-3">
                <span className="text-sm font-semibold text-orange-500">{event.signal_score.toFixed(1)}</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
      {!isLoading && filtered.length === 0 && (
        <p className="text-sm text-gray-400 text-center py-8">No events match the filter.</p>
      )}
    </div>
  );
}
