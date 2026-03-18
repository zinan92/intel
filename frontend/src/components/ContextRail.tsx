import type { FeedContext } from "../types/api";

interface Props {
  context: FeedContext | undefined;
}

export function ContextRail({ context }: Props) {
  const rising = context?.rising_topics ?? [];
  const health = context?.source_health ?? [];

  if (!context) {
    return (
      <aside className="w-52 shrink-0 hidden xl:block">
        <div className="sticky top-20 space-y-4 animate-pulse">
          <div className="h-4 bg-gray-100 rounded w-24" />
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-3 bg-gray-100 rounded" />
            ))}
          </div>
        </div>
      </aside>
    );
  }

  return (
    <aside className="w-52 shrink-0 hidden xl:block">
      <div className="sticky top-20 space-y-6 pl-2">
        {rising.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Rising Topics</p>
            <ul className="space-y-1">
              {rising.slice(0, 8).map((t) => (
                <li key={t.topic} className="flex items-center justify-between gap-2 text-sm">
                  <span className="text-gray-700 truncate">{t.topic}</span>
                  <span className="text-xs text-gray-400 shrink-0">{t.count}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {context?.top_events && context.top_events.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Active Events</p>
            <ul className="space-y-1.5">
              {context.top_events.slice(0, 5).map((e) => (
                <li key={e.id} className="text-sm">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-gray-700 truncate">{e.narrative_tag.replace(/-/g, " ")}</span>
                    <span className="text-xs text-orange-500 font-medium shrink-0">{e.signal_score.toFixed(1)}</span>
                  </div>
                  <span className="text-xs text-gray-400">{e.source_count} sources · {e.article_count} articles</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {health.length > 0 && (() => {
          const okCount = health.filter((h) => h.status === "ok").length;
          const degradedCount = health.filter((h) => h.status === "degraded").length;
          const staleCount = health.filter((h) => h.status === "stale").length;
          const total = health.length;
          return (
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Pipeline</p>
              <div className="flex items-center gap-1 mb-1.5">
                {health.map((h) => {
                  const dot =
                    h.status === "ok" ? "bg-green-400"
                    : h.status === "degraded" ? "bg-red-400"
                    : h.status === "stale" ? "bg-amber-400"
                    : "bg-gray-300";
                  return <span key={h.source} className={`w-2 h-2 rounded-full ${dot}`} title={h.status} />;
                })}
              </div>
              <p className="text-xs text-gray-500">
                {okCount}/{total} healthy
                {degradedCount > 0 && <span className="text-red-500"> · {degradedCount} degraded</span>}
                {staleCount > 0 && <span className="text-amber-500"> · {staleCount} stale</span>}
              </p>
            </div>
          );
        })()}
      </div>
    </aside>
  );
}
