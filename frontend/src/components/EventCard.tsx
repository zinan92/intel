import { Link } from "react-router-dom";
import type { TopEvent } from "../types/api";

export function VelocityArrow({ current, prev }: { current: number; prev: number | null }) {
  if (prev === null) return <span className="text-blue-400 text-[10px] font-semibold ml-1">NEW</span>;
  if (current > prev) return <span className="text-green-400 ml-1">↑</span>;
  if (current < prev) return <span className="text-red-400 ml-1">↓</span>;
  return <span className="text-slate-500 ml-1">→</span>;
}

interface Props {
  event: TopEvent;
}

export function EventCard({ event }: Props) {
  const scoreColor = event.signal_score >= 8 ? "text-orange-500" : "text-yellow-500";

  return (
    <Link
      to={`/events/${event.id}`}
      className="block bg-surface-card border border-surface-border rounded-lg p-3 hover:border-brand-500/30 transition-all"
    >
      <div className={`text-[10px] font-semibold uppercase ${scoreColor} font-mono`}>
        Signal {event.signal_score.toFixed(1)}
        <VelocityArrow current={event.signal_score} prev={event.prev_signal_score} />
      </div>
      <div className="text-sm font-semibold text-slate-200 mt-0.5 line-clamp-1">
        {event.narrative_tag.replace(/-/g, " ")}
      </div>
      <div className="text-xs text-slate-400 mt-1">
        {event.source_count} sources
        {event.tickers.length > 0 && (
          <span className="ml-1.5 font-mono text-brand-400/70">
            · {event.tickers.slice(0, 2).map(t => `$${t}`).join(" ")}
          </span>
        )}
      </div>
    </Link>
  );
}
