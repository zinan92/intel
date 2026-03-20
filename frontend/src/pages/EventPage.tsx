import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { ItemDrawer } from "../components/ItemDrawer";

function formatTimeAgo(iso: string | null): string {
  if (!iso) return "";
  const utcIso = iso.endsWith("Z") ? iso : iso + "Z";
  const diff = Date.now() - new Date(utcIso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function parseTradingPlay(play: string | null): { bullPct: number; bullText: string; bearPct: number; bearText: string } | null {
  if (!play) return null;

  const bullPctMatch = play.match(/BULL_PCT:\s*(\d+)/);
  const bearPctMatch = play.match(/BEAR_PCT:\s*(\d+)/);
  const bullTextMatch = play.match(/BULL:\s*(.+?)(?=\n\n|BEAR_PCT|$)/s);
  const bearTextMatch = play.match(/BEAR:\s*(.+?)$/s);

  // Fallback for old SCENARIO format
  if (!bullPctMatch) {
    const scenarioA = play.match(/SCENARIO A:\s*(.+?)(?=SCENARIO B|$)/s);
    const scenarioB = play.match(/SCENARIO B:\s*(.+?)$/s);
    if (scenarioA && scenarioB) {
      return { bullPct: 50, bullText: scenarioA[1].trim(), bearPct: 50, bearText: scenarioB[1].trim() };
    }
    return null;
  }

  return {
    bullPct: parseInt(bullPctMatch[1], 10),
    bullText: bullTextMatch ? bullTextMatch[1].trim() : "",
    bearPct: bearPctMatch ? parseInt(bearPctMatch[1], 10) : 100 - parseInt(bullPctMatch[1], 10),
    bearText: bearTextMatch ? bearTextMatch[1].trim() : "",
  };
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

  const { data: scorecard } = useQuery({
    queryKey: ["scorecard"],
    queryFn: () => api.scorecard({ days: 30, min_events: 2 }),
    staleTime: 300_000,
  });

  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-6 bg-slate-800 rounded w-48" />
        <div className="h-20 bg-slate-800 rounded-lg" />
        <div className="h-40 bg-slate-800 rounded-lg" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-sm text-red-400 bg-red-500/10 px-4 py-3 rounded-lg">
        Failed to load event. <Link to="/" className="underline">Back to Signals</Link>
      </div>
    );
  }

  const matchingBucket = scorecard?.buckets.find(b => {
    const score = data?.event.signal_score ?? 0;
    if (b.label.includes("8") && score >= 8) return true;
    if (b.label.includes("6") && score >= 6 && score < 8) return true;
    if (b.label.includes("4") && score >= 4 && score < 6) return true;
    if (b.min_score === 0 && score < 4) return true;
    return false;
  });

  const { event, articles, price_impacts } = data;
  const sortedArticles = [...articles].sort((a, b) => {
    const ta = a.published_at || a.collected_at || "";
    const tb = b.published_at || b.collected_at || "";
    return tb.localeCompare(ta);
  });

  return (
    <div className="max-w-2xl">
      <Link to="/" className="text-sm text-slate-500 hover:text-slate-300 mb-4 inline-block">
        &larr; Back to Signals
      </Link>

      <div className="flex justify-between items-start mb-3">
        <div>
          <h1 className="text-2xl font-bold text-white">
            {event.narrative_tag.replace(/-/g, " ")}
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">
            {event.source_count} sources &middot; {event.article_count} articles &middot; {formatTimeAgo(event.window_start)}
          </p>
        </div>
        <div className="shrink-0 ml-4">
          <div className="bg-brand-500 text-slate-950 text-lg font-bold font-mono px-3.5 py-1.5 rounded-lg">
            {event.signal_score.toFixed(1)}
          </div>
          {data.event.prev_signal_score !== null && (
            <p className="text-xs text-slate-500 font-mono mt-1">
              {data.event.signal_score > data.event.prev_signal_score ? "↑" : data.event.signal_score < data.event.prev_signal_score ? "↓" : "→"}
              {" "}from {data.event.prev_signal_score.toFixed(1)}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-4">
        {Array.from(new Set(articles.map(a => a.source))).map((source) => (
          <span key={source} className="bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[10px] px-2 py-0.5 rounded-full">
            {source}
          </span>
        ))}
      </div>

      {data.event.narrative_summary && (
        <p className="text-sm text-slate-300 mb-4">{data.event.narrative_summary}</p>
      )}

      {data.event.trading_play && (() => {
        const tp = parseTradingPlay(data.event.trading_play);
        if (!tp) {
          return (
            <div className="bg-slate-800/50 border border-surface-border rounded-lg p-4 mb-5">
              <p className="text-[9px] text-slate-400 uppercase tracking-wider mb-3">Trading Consideration</p>
              <p className="text-sm text-slate-300">{data.event.trading_play}</p>
              <p className="text-[10px] text-slate-500 mt-3 pt-2 border-t border-surface-border">
                AI-generated analysis. Not financial advice.
              </p>
            </div>
          );
        }
        return (
          <div className="bg-slate-800/50 border border-surface-border rounded-lg p-4 mb-5">
            <p className="text-[9px] text-slate-400 uppercase tracking-wider mb-3">Scenario Analysis</p>

            {/* Probability bar */}
            <div className="flex h-2 rounded-full overflow-hidden mb-3">
              <div className="bg-green-500/60" style={{ width: `${tp.bullPct}%` }} />
              <div className="bg-red-500/60" style={{ width: `${tp.bearPct}%` }} />
            </div>

            <div className="grid grid-cols-2 gap-3">
              {/* Bull */}
              <div className="bg-green-500/5 border border-green-500/10 rounded-lg p-3">
                <div className="flex items-center gap-1.5 mb-1.5">
                  <span className="text-green-400 text-xs font-semibold">BULL</span>
                  <span className="text-green-400/70 text-xs font-mono">{tp.bullPct}%</span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">{tp.bullText}</p>
              </div>
              {/* Bear */}
              <div className="bg-red-500/5 border border-red-500/10 rounded-lg p-3">
                <div className="flex items-center gap-1.5 mb-1.5">
                  <span className="text-red-400 text-xs font-semibold">BEAR</span>
                  <span className="text-red-400/70 text-xs font-mono">{tp.bearPct}%</span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">{tp.bearText}</p>
              </div>
            </div>

            <p className="text-[10px] text-slate-500 mt-3 pt-2 border-t border-surface-border">
              AI-generated analysis. Not financial advice.
            </p>
          </div>
        );
      })()}

      {matchingBucket && (
        <div className="bg-slate-800/30 border border-surface-border rounded-lg p-4 mb-5">
          <p className="text-[9px] text-slate-400 uppercase tracking-wider mb-2">Historical Context</p>
          <p className="text-xs text-slate-400 mb-2">
            {matchingBucket.label} ({matchingBucket.event_count} events, {scorecard?.period_days}d)
          </p>
          <div className="flex gap-6 font-mono text-sm">
            <div>
              <span className="text-[10px] text-slate-500">Avg 1D </span>
              <span className={matchingBucket.avg_change_1d >= 0 ? "text-green-400" : "text-red-400"}>
                {matchingBucket.avg_change_1d >= 0 ? "+" : ""}{matchingBucket.avg_change_1d.toFixed(1)}%
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500">Avg 3D </span>
              <span className={matchingBucket.avg_change_3d >= 0 ? "text-green-400" : "text-red-400"}>
                {matchingBucket.avg_change_3d >= 0 ? "+" : ""}{matchingBucket.avg_change_3d.toFixed(1)}%
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500">Avg 5D </span>
              <span className={matchingBucket.avg_change_5d >= 0 ? "text-green-400" : "text-red-400"}>
                {matchingBucket.avg_change_5d >= 0 ? "+" : ""}{matchingBucket.avg_change_5d.toFixed(1)}%
              </span>
            </div>
          </div>
        </div>
      )}

      {price_impacts.length > 0 && (
        <div className="bg-slate-800/80 border border-surface-border rounded-lg p-4 mb-5">
          <p className="text-[9px] text-slate-500 uppercase tracking-wider font-mono mb-2">Price Impact</p>
          <div className="flex gap-6">
            {price_impacts.map((pi) => (
              <div key={pi.ticker}>
                <div className="text-xs text-slate-400 font-mono">${pi.ticker}</div>
                <div className="text-xs text-slate-500 font-mono">{pi.price_at_event.toLocaleString()}</div>
                <div className="flex gap-2 mt-1">
                  <span className="text-[10px] text-slate-500 font-mono">1D</span><PriceChange value={pi.change_1d} />
                  <span className="text-[10px] text-slate-500 font-mono">3D</span><PriceChange value={pi.change_3d} />
                  <span className="text-[10px] text-slate-500 font-mono">5D</span><PriceChange value={pi.change_5d} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-[9px] text-slate-500 uppercase tracking-wider font-mono mb-3">Timeline</p>
      <div className="border-l-2 border-slate-700 pl-4 space-y-4">
        {sortedArticles.map((article, idx) => {
          const dotColor = idx === 0 ? "bg-green-500" : "bg-blue-500";
          const timeStr = formatTimeAgo(article.published_at || article.collected_at);
          return (
            <div key={article.id} className="relative">
              <div className={`absolute -left-[21px] top-1.5 w-2 h-2 rounded-full ${dotColor}`} />
              <div className="text-xs text-slate-500">{timeStr} &middot; {article.source}</div>
              <button
                onClick={() => setSelectedArticleId(article.id)}
                className="text-sm font-medium text-slate-200 hover:text-brand-400 text-left mt-0.5"
              >
                {article.title || "Untitled"}
              </button>
              {article.summary && (
                <p className="text-xs text-slate-500 mt-0.5 line-clamp-1">{article.summary}</p>
              )}
            </div>
          );
        })}
      </div>

      <ItemDrawer itemId={selectedArticleId} onClose={() => setSelectedArticleId(null)} />
    </div>
  );
}
