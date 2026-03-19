import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { ItemDrawer } from "../components/ItemDrawer";

function formatTimeAgo(iso: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function PriceChange({ value }: { value: number }) {
  const color = value >= 0 ? "text-green-400" : "text-red-400";
  const sign = value >= 0 ? "+" : "";
  return <span className={`text-xs ${color}`}>{sign}{value.toFixed(1)}%</span>;
}

export function EventPage() {
  const { id } = useParams<{ id: string }>();
  const eventId = parseInt(id ?? "0", 10);
  const [selectedArticleId, setSelectedArticleId] = useState<number | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api.eventDetail(eventId),
    enabled: eventId > 0,
  });

  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-6 bg-gray-100 rounded w-48" />
        <div className="h-20 bg-gray-100 rounded-xl" />
        <div className="h-40 bg-gray-100 rounded-lg" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-sm text-red-500 bg-red-50 px-4 py-3 rounded-lg">
        Failed to load event. <Link to="/" className="underline">Back to Brief</Link>
      </div>
    );
  }

  const { event, articles, price_impacts } = data;
  const sortedArticles = [...articles].sort((a, b) => {
    const ta = a.published_at || a.collected_at || "";
    const tb = b.published_at || b.collected_at || "";
    return tb.localeCompare(ta);
  });

  return (
    <div className="max-w-2xl">
      <Link to="/" className="text-sm text-gray-500 hover:text-gray-700 mb-4 inline-block">
        &larr; Back to Brief
      </Link>

      <div className="flex justify-between items-start mb-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">
            {event.narrative_tag.replace(/-/g, " ")}
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {event.source_count} sources &middot; {event.article_count} articles &middot; {formatTimeAgo(event.window_start)}
          </p>
        </div>
        <div className="bg-orange-500 text-white text-lg font-bold px-3.5 py-1.5 rounded-lg shrink-0 ml-4">
          {event.signal_score.toFixed(1)}
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-4">
        {Array.from(new Set(articles.map(a => a.source))).map((source) => (
          <span key={source} className="bg-blue-100 text-blue-700 text-[10px] px-2 py-0.5 rounded-full">
            {source}
          </span>
        ))}
      </div>

      {price_impacts.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-4 mb-5">
          <p className="text-[9px] text-slate-400 uppercase tracking-wider mb-2">Price Impact</p>
          <div className="flex gap-6">
            {price_impacts.map((pi) => (
              <div key={pi.ticker}>
                <div className="text-xs text-slate-400">${pi.ticker}</div>
                <div className="text-xs text-slate-500">{pi.price_at_event.toLocaleString()}</div>
                <div className="flex gap-2 mt-1">
                  <span className="text-[10px] text-slate-500">1D</span><PriceChange value={pi.change_1d} />
                  <span className="text-[10px] text-slate-500">3D</span><PriceChange value={pi.change_3d} />
                  <span className="text-[10px] text-slate-500">5D</span><PriceChange value={pi.change_5d} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-[9px] text-gray-400 uppercase tracking-wider mb-3">Timeline</p>
      <div className="border-l-2 border-gray-200 pl-4 space-y-4">
        {sortedArticles.map((article, idx) => {
          const dotColor = idx === 0 ? "bg-green-500" : "bg-blue-500";
          const timeStr = formatTimeAgo(article.published_at || article.collected_at);
          return (
            <div key={article.id} className="relative">
              <div className={`absolute -left-[21px] top-1.5 w-2 h-2 rounded-full ${dotColor}`} />
              <div className="text-xs text-gray-400">{timeStr} &middot; {article.source}</div>
              <button
                onClick={() => setSelectedArticleId(article.id)}
                className="text-sm font-medium text-gray-800 hover:text-brand-600 text-left mt-0.5"
              >
                {article.title || "Untitled"}
              </button>
              {article.summary && (
                <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{article.summary}</p>
              )}
            </div>
          );
        })}
      </div>

      <ItemDrawer itemId={selectedArticleId} onClose={() => setSelectedArticleId(null)} />
    </div>
  );
}
