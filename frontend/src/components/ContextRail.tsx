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

        {health.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Sources</p>
            <ul className="space-y-1">
              {health.slice(0, 8).map((h) => {
                const dot =
                  h.status === "ok" ? "bg-green-400"
                  : h.status === "degraded" ? "bg-red-400"
                  : h.status === "stale" ? "bg-amber-400"
                  : "bg-gray-300"; // no_data
                return (
                  <li key={h.source} className="flex items-center gap-1.5 text-sm">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dot}`} />
                    <span className="text-gray-700 truncate">{h.source}</span>
                    <span className="ml-auto text-xs text-gray-400 shrink-0">{h.count || "—"}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </aside>
  );
}
