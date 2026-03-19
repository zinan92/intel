import { Link } from "react-router-dom";
import type { TopEvent } from "../types/api";

interface Props {
  event: TopEvent;
}

export function EventCard({ event }: Props) {
  const scoreColor = event.signal_score >= 8 ? "text-orange-500" : "text-yellow-500";

  return (
    <Link
      to={`/events/${event.id}`}
      className="block bg-white border border-gray-200 rounded-lg p-3 hover:border-brand-400 hover:shadow-sm transition-all"
    >
      <div className={`text-[10px] font-semibold uppercase ${scoreColor}`}>
        Signal {event.signal_score.toFixed(1)}
      </div>
      <div className="text-sm font-semibold text-gray-800 mt-0.5 line-clamp-1">
        {event.narrative_tag.replace(/-/g, " ")}
      </div>
      <div className="text-xs text-gray-500 mt-1">
        {event.source_count} sources
        {event.tickers.length > 0 && (
          <span className="ml-1.5 text-gray-400">
            · {event.tickers.slice(0, 2).map(t => `$${t}`).join(" ")}
          </span>
        )}
      </div>
    </Link>
  );
}
