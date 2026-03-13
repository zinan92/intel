import type { FeedItem } from "../types/api";

const KIND_COLORS: Record<string, string> = {
  release: "bg-violet-100 text-violet-700",
  discussion: "bg-blue-100 text-blue-700",
  blog: "bg-emerald-100 text-emerald-700",
  post: "bg-amber-100 text-amber-700",
  trend: "bg-cyan-100 text-cyan-700",
  news: "bg-gray-100 text-gray-600",
};

const MOMENTUM_COLORS: Record<string, string> = {
  trending: "text-green-600",
  rising: "text-emerald-500",
  stable: "text-gray-400",
  fading: "text-red-300",
};

function formatAge(iso: string | null): string {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 3600) return `${Math.round(diff / 60)}m`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h`;
  return `${Math.round(diff / 86400)}d`;
}

interface Props {
  item: FeedItem;
  onClick: (item: FeedItem) => void;
}

export function FeedCard({ item, onClick }: Props) {
  const kindClass = KIND_COLORS[item.source_kind] ?? KIND_COLORS.news;
  const momentumClass = MOMENTUM_COLORS[item.momentum_label] ?? "text-gray-400";

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onClick(item)}
      onKeyDown={(e) => e.key === "Enter" && onClick(item)}
      className="bg-white border border-gray-200 rounded-lg px-4 py-3 hover:border-brand-300 hover:shadow-sm cursor-pointer transition-all outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${kindClass}`}>
            {item.source_kind}
          </span>
          <span className="text-xs text-gray-400">{item.source}</span>
        </div>
        <div className="flex items-center gap-2 text-xs shrink-0">
          <span className={`font-medium ${momentumClass}`}>{item.momentum_label}</span>
          <span className="text-gray-400">{formatAge(item.collected_at)}</span>
        </div>
      </div>

      <h2 className="mt-2 text-sm font-semibold text-gray-900 leading-snug line-clamp-2">
        {item.title ?? "(no title)"}
      </h2>

      {item.summary && (
        <p className="mt-1 text-xs text-gray-500 line-clamp-2 leading-relaxed">
          {item.summary}
        </p>
      )}

      <div className="mt-2 flex flex-wrap gap-1">
        {item.narrative_tags.slice(0, 3).map((t) => (
          <span key={t} className="text-xs bg-brand-50 text-brand-600 px-1.5 py-0.5 rounded">
            {t}
          </span>
        ))}
        {item.tags.slice(0, 3).map((t) => (
          <span key={t} className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
            {t}
          </span>
        ))}
      </div>

      <div className="mt-2 flex items-center justify-between text-xs text-gray-400">
        <span>rel {item.relevance_score ?? "—"}/5</span>
        <span className="font-mono">score {item.priority_score.toFixed(2)}</span>
      </div>
    </article>
  );
}
