import { useState } from "react";
import type { HealthSource } from "../types/api";

const STATUS_DOT: Record<string, string> = {
  ok: "bg-green-400",
  stale: "bg-amber-400",
  degraded: "bg-red-400",
  error: "bg-red-400",
  disabled: "bg-slate-500",
  no_data: "bg-slate-500",
};

const STATUS_LABEL: Record<string, string> = {
  ok: "Healthy",
  stale: "Stale",
  degraded: "Degraded",
  error: "Error",
  disabled: "Disabled",
  no_data: "No Data",
};

function formatFreshness(hours: number | null): string {
  if (hours === null) return "No data";
  if (hours < 1) return "< 1h ago";
  return `${Math.round(hours)}h ago`;
}

interface Props {
  source: HealthSource;
}

export function SourceCard({ source }: Props) {
  const [showError, setShowError] = useState(false);

  const isDisabled = source.status === "disabled" || !source.is_active;
  const dotColor = STATUS_DOT[source.status] ?? "bg-slate-500";
  const statusLabel = STATUS_LABEL[source.status] ?? source.status;

  return (
    <div
      className={`rounded-lg p-4 border transition-colors ${
        isDisabled
          ? "bg-slate-800/20 border-surface-border opacity-60"
          : "bg-slate-800/50 border-surface-border"
      }`}
    >
      {/* Header: status dot + name + status label */}
      <div className="flex items-center gap-2 mb-3">
        <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${dotColor}`} />
        <span className="text-sm font-medium text-slate-200 truncate">
          {source.display_name}
        </span>
        <span className="text-xs text-slate-500 ml-auto">{statusLabel}</span>
      </div>

      {/* Metrics row */}
      <div className="flex items-center gap-4 text-xs text-slate-400 mb-2">
        <div>
          <span className="text-slate-500">Freshness: </span>
          <span>{formatFreshness(source.freshness_age_hours)}</span>
        </div>
        <div>
          <span className="text-slate-500">24h: </span>
          <span className="text-slate-300">{source.articles_24h}</span>
        </div>
        {source.articles_7d_avg !== null && (
          <div>
            <span className="text-slate-500">7d avg: </span>
            <span>{source.articles_7d_avg.toFixed(1)}</span>
          </div>
        )}
      </div>

      {/* Volume anomaly flag */}
      {source.volume_anomaly === true && (
        <p className="text-xs text-red-400 font-medium mb-2">
          Volume low
        </p>
      )}

      {/* Disabled reason */}
      {isDisabled && source.disabled_reason && (
        <div className="text-xs text-slate-500 bg-slate-900/50 rounded px-2 py-1.5 mt-2">
          <span className="text-slate-400 font-medium">How to enable: </span>
          {source.disabled_reason}
        </div>
      )}

      {/* Last error (expandable) */}
      {source.last_error && !isDisabled && (
        <div className="mt-2">
          <button
            onClick={() => setShowError((prev) => !prev)}
            className="text-xs text-slate-500 hover:text-slate-400 transition-colors"
          >
            {showError ? "Hide error" : "Show last error"}
          </button>
          {showError && (
            <pre className="text-xs text-red-400/80 bg-slate-900/50 rounded px-2 py-1.5 mt-1 whitespace-pre-wrap break-words max-h-24 overflow-auto">
              {source.last_error}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
