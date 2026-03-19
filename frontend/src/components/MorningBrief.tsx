import { Link } from "react-router-dom";
import { EventCard, VelocityArrow } from "./EventCard";
import type { TopEvent } from "../types/api";

interface Props {
  events: TopEvent[];
}

export function MorningBrief({ events }: Props) {
  if (events.length === 0) return null;

  const [hero, ...rest] = events;
  const gridEvents = rest.slice(0, 4);

  const today = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="mb-6">
      <p className="text-xs text-gray-400 uppercase tracking-wider mb-3">
        {today} · Morning Brief
      </p>

      <Link
        to={`/events/${hero.id}`}
        className="block bg-gradient-to-br from-slate-800 to-slate-700 rounded-xl p-4 mb-3 hover:from-slate-700 hover:to-slate-600 transition-all"
      >
        <div className="flex justify-between items-start">
          <div>
            <div className="text-[10px] font-semibold text-orange-400 uppercase tracking-wide">
              Signal {hero.signal_score.toFixed(1)}
              <VelocityArrow current={hero.signal_score} prev={hero.prev_signal_score} />
              {" "}· {hero.source_count} sources
            </div>
            <div className="text-base font-semibold text-white mt-1">
              {hero.narrative_tag.replace(/-/g, " ")}
            </div>
            <div className="text-xs text-slate-400 mt-1">
              {hero.sources.join(" · ")}
            </div>
            {hero.narrative_summary && (
              <p className="text-xs text-slate-300 mt-2 line-clamp-2">
                {hero.narrative_summary}
              </p>
            )}
          </div>
          {hero.tickers.length > 0 && (
            <div className="text-right shrink-0 ml-4">
              <div className="text-xs text-slate-400">
                {hero.tickers.slice(0, 3).map(t => `$${t}`).join(" · ")}
              </div>
            </div>
          )}
        </div>
      </Link>

      {gridEvents.length > 0 && (
        <div className="grid grid-cols-2 gap-3 mb-4">
          {gridEvents.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </div>
      )}

      <p className="text-xs text-gray-400 uppercase tracking-wider mt-2">
        Latest Feed
      </p>
    </div>
  );
}
