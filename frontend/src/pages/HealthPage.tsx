import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { SourceCard } from "../components/SourceCard";
import type { HealthSource } from "../types/api";

function bannerColor(healthy: number, total: number): string {
  if (total === 0) return "text-slate-400";
  const ratio = healthy / total;
  if (ratio >= 0.8) return "text-green-400";
  if (ratio >= 0.5) return "text-amber-400";
  return "text-red-400";
}

function partitionSources(sources: HealthSource[]): {
  active: HealthSource[];
  disabled: HealthSource[];
} {
  const active: HealthSource[] = [];
  const disabled: HealthSource[] = [];
  for (const s of sources) {
    if (s.status === "disabled" || !s.is_active) {
      disabled.push(s);
    } else {
      active.push(s);
    }
  }
  return { active, disabled };
}

export function HealthPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["health", "sources"],
    queryFn: () => api.healthSources(),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const sources = data?.sources ?? [];
  const healthyCount = sources.filter((s) => s.status === "ok").length;
  const totalActive = sources.filter((s) => s.is_active).length;
  const { active, disabled } = partitionSources(sources);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-lg font-semibold text-slate-200">
          数据健康
        </h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Source collection status and freshness monitoring
        </p>
      </div>

      {/* Restart loop warning */}
      {!isLoading && !isError && data?.process?.restart_loop_warning && (
        <div className="bg-red-900/30 border border-red-500/50 rounded-lg px-4 py-3 text-sm text-red-300">
          Service uptime is under 10 minutes — possible restart loop. Check{" "}
          <code className="text-red-200">logs/park-intel-stderr.log</code> for errors.
        </div>
      )}

      {/* Health banner */}
      {!isLoading && !isError && data && (
        <div className="bg-slate-800/50 border border-surface-border rounded-lg px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className={`text-xl font-bold ${bannerColor(healthyCount, totalActive)}`}>
              {healthyCount}/{totalActive}
            </span>
            <span className="text-sm text-slate-400">sources healthy</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`w-2 h-2 rounded-full ${data.scheduler_alive ? "bg-green-400" : "bg-red-400"}`}
            />
            <span className={data.scheduler_alive ? "text-slate-400" : "text-red-400 font-medium"}>
              {data.scheduler_alive ? "Scheduler alive" : "Scheduler dead"}
            </span>
          </div>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-32 bg-slate-800 rounded-lg animate-pulse" />
          ))}
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="text-sm text-red-400 bg-red-500/10 px-4 py-3 rounded-lg flex items-center justify-between">
          <span>Failed to load health data. Check that the API is running on port 8001.</span>
          <button
            onClick={() => refetch()}
            className="text-xs text-red-300 hover:text-red-200 border border-red-500/30 rounded px-2 py-1 transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Active source cards */}
      {!isLoading && active.length > 0 && (
        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono mb-3">
            Active Sources ({active.length})
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {active.map((source) => (
              <SourceCard key={source.source_type} source={source} />
            ))}
          </div>
        </div>
      )}

      {/* Disabled source cards */}
      {!isLoading && disabled.length > 0 && (
        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono mb-3">
            Disabled Sources ({disabled.length})
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {disabled.map((source) => (
              <SourceCard key={source.source_type} source={source} />
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !isError && sources.length === 0 && (
        <div className="text-sm text-slate-500 text-center py-12">
          No sources configured.
        </div>
      )}
    </div>
  );
}
