import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

function formatBriefAge(iso: string | null): string {
  if (!iso) return "";
  const utcIso = iso.endsWith("Z") ? iso : iso + "Z";
  const diff = Date.now() - new Date(utcIso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function NarrativeSignal() {
  const { data, isLoading } = useQuery({
    queryKey: ["latest-brief"],
    queryFn: () => api.latestBrief(),
    staleTime: 120_000, // 2 min
  });

  if (isLoading) {
    return (
      <div className="mb-6 animate-pulse">
        <div className="h-4 bg-slate-800 rounded w-48 mb-3" />
        <div className="h-64 bg-slate-800/50 rounded-lg" />
      </div>
    );
  }

  const brief = data?.brief;
  if (!brief) return null;

  // Parse the markdown-like content into styled sections
  const lines = brief.content.split("\n");

  return (
    <div className="mb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono">
          Narrative Signal
        </p>
        <span className="text-[10px] text-slate-600 font-mono">
          {formatBriefAge(brief.created_at)} · {brief.article_count} articles
        </span>
      </div>

      {/* Content */}
      <div className="bg-surface-card border border-surface-border rounded-lg p-5 space-y-1">
        {lines.map((line, i) => {
          const trimmed = line.trim();
          if (!trimmed) return <div key={i} className="h-2" />;

          // Header line with emoji
          if (trimmed.startsWith("\uD83C\uDFAF")) {
            return (
              <p key={i} className="text-sm font-semibold text-slate-200 pb-1">
                {trimmed}
              </p>
            );
          }

          // Stats line
          if (trimmed.startsWith("\uD83D\uDCCA")) {
            return (
              <p key={i} className="text-xs text-slate-400 font-mono pb-2 border-b border-surface-border">
                {trimmed}
              </p>
            );
          }

          // Section headers
          if (trimmed.includes("\u2501\u2501\u2501")) {
            return (
              <p key={i} className="text-xs font-semibold text-brand-400 pt-3 pb-1">
                {trimmed.replace(/\u2501/g, "").trim()}
              </p>
            );
          }

          // Numbered signal items (bold)
          if (/^\d+\.\s*\*\*/.test(trimmed)) {
            const cleaned = trimmed.replace(/\*\*/g, "");
            return (
              <p key={i} className="text-sm font-semibold text-slate-200 pt-2">
                {cleaned}
              </p>
            );
          }

          // Arrow lines
          if (trimmed.startsWith("\u2192")) {
            return (
              <p key={i} className="text-xs text-slate-400 pl-4 leading-relaxed">
                {trimmed}
              </p>
            );
          }

          // Bullet points
          if (trimmed.startsWith("\u2022")) {
            return (
              <p key={i} className="text-xs text-slate-400 pl-2 leading-relaxed">
                {trimmed}
              </p>
            );
          }

          // Cross-narrative / quant check headers
          if (trimmed.startsWith("\u26A1\uFE0F") || trimmed.startsWith("\uD83D\uDD17")) {
            return (
              <p key={i} className="text-xs font-semibold text-slate-300 pt-3 pb-1">
                {trimmed}
              </p>
            );
          }

          // Sources line
          if (trimmed.startsWith("Sources:") || trimmed.startsWith("---")) {
            return (
              <p key={i} className="text-[10px] text-slate-600 pt-2 border-t border-surface-border mt-2">
                {trimmed === "---" ? "" : trimmed}
              </p>
            );
          }

          // Default text
          return (
            <p key={i} className="text-xs text-slate-400 leading-relaxed">
              {trimmed}
            </p>
          );
        })}
      </div>
    </div>
  );
}
