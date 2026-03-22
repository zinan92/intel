import type { FeedItem } from "../types/api";

/** Strip HTML tags from text content. Handles truncated tags too. */
export function stripHtml(html: string): string {
  return html
    .replace(/<[^>]*>?/g, "")  // remove tags, including truncated ones without closing >
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#\d+;/g, " ")
    .replace(/\s{2,}/g, " ")  // collapse whitespace
    .trim();
}

const KIND_COLORS: Record<string, string> = {
  release: "bg-violet-500/10 text-violet-400",
  discussion: "bg-blue-500/10 text-blue-400",
  blog: "bg-emerald-500/10 text-emerald-400",
  post: "bg-amber-500/10 text-amber-400",
  trend: "bg-cyan-500/10 text-cyan-400",
  news: "bg-slate-500/10 text-slate-400",
};

const MOMENTUM_COLORS: Record<string, string> = {
  trending: "text-green-400",
  rising: "text-green-400",
  stable: "text-slate-500",
  fading: "text-red-400",
};

function formatAge(iso: string | null): string {
  if (!iso) return "";
  // API returns UTC timestamps without Z suffix — append Z so JS parses as UTC
  const utcIso = iso.endsWith("Z") ? iso : iso + "Z";
  const diff = (Date.now() - new Date(utcIso).getTime()) / 1000;
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
  const momentumClass = MOMENTUM_COLORS[item.momentum_label] ?? "text-slate-500";

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onClick(item)}
      onKeyDown={(e) => e.key === "Enter" && onClick(item)}
      className="bg-surface-card border border-surface-border rounded-lg px-4 py-3 hover:border-surface-muted cursor-pointer transition-all outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${kindClass}`}>
            {item.source_kind}
          </span>
          {item.in_event && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-brand-500/10 text-brand-400">
              event
            </span>
          )}
          <span className="text-xs text-slate-500">{item.source}</span>
        </div>
        <div className="flex items-center gap-2 text-xs shrink-0">
          <span className={`font-medium ${momentumClass}`}>{item.momentum_label}</span>
          <span className="text-slate-500">{formatAge(item.collected_at)}</span>
        </div>
      </div>

      <h2 className="mt-2 text-sm font-semibold text-slate-100 leading-snug line-clamp-2">
        {item.title ?? "(no title)"}
      </h2>

      {item.summary && (
        <p className="mt-1 text-xs text-slate-400 line-clamp-2 leading-relaxed">
          {stripHtml(item.summary)}
        </p>
      )}

      <div className="mt-2 flex flex-wrap gap-1">
        {item.narrative_tags.slice(0, 3).map((t) => (
          <span key={t} className="text-xs bg-brand-500/10 text-brand-400 px-1.5 py-0.5 rounded">
            {t}
          </span>
        ))}
        {item.tags.slice(0, 3).map((t) => (
          <span key={t} className="text-xs bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded">
            {t}
          </span>
        ))}
      </div>

    </article>
  );
}
