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
          <div className="h-4 bg-slate-800 rounded w-24" />
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-3 bg-slate-800 rounded" />
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
            <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono mb-2">Rising Topics</p>
            <ul className="space-y-1">
              {rising.slice(0, 8).map((t) => (
                <li key={t.topic} className="flex items-center justify-between gap-2 text-sm">
                  <span className="text-slate-300 truncate">{t.topic}</span>
                  <span className="text-xs text-slate-500 font-mono shrink-0">{t.count}</span>
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
              <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono mb-2">Pipeline</p>
              <div className="flex items-center gap-1 mb-1.5">
                {health.map((h) => {
                  const dot =
                    h.status === "ok" ? "bg-green-400"
                    : h.status === "degraded" ? "bg-red-400"
                    : h.status === "stale" ? "bg-amber-400"
                    : "bg-slate-500";
                  return <span key={h.source} className={`w-2 h-2 rounded-full ${dot}`} title={h.status} />;
                })}
              </div>
              <p className="text-xs text-slate-400">
                {okCount}/{total} healthy
                {degradedCount > 0 && <span className="text-red-400"> · {degradedCount} degraded</span>}
                {staleCount > 0 && <span className="text-amber-400"> · {staleCount} stale</span>}
              </p>
            </div>
          );
        })()}
      </div>
    </aside>
  );
}
