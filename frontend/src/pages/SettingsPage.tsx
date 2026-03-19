import { useState, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useSearchParams } from "react-router-dom";

const TOPICS = [
  "ai", "crypto", "macro", "geopolitics", "china-market", "us-market",
  "sector/tech", "sector/finance", "sector/energy",
  "trading", "regulation", "earnings", "commodities",
];

export function SettingsPage() {
  const [params] = useSearchParams();
  const username = params.get("user") ?? "";
  const queryClient = useQueryClient();

  const { data: user, isLoading } = useQuery({
    queryKey: ["user", username],
    queryFn: () => api.user(username),
    enabled: !!username,
  });

  const mutation = useMutation({
    mutationFn: (weights: Record<string, number>) =>
      api.updateWeights(username, weights),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user", username] });
    },
  });

  const [localWeights, setLocalWeights] = useState<Record<string, number>>({});
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  const weights = { ...(user?.topic_weights ?? {}), ...localWeights };

  const handleChange = useCallback((topic: string, value: number) => {
    setLocalWeights((prev) => ({ ...prev, [topic]: value }));
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      const updated = { ...(user?.topic_weights ?? {}), ...localWeights, [topic]: value };
      mutation.mutate(updated);
      setLocalWeights({});
    }, 500);
  }, [user, localWeights, mutation]);

  if (!username) {
    return <div className="text-sm text-slate-500 py-8">Select a user from the sidebar to configure weights.</div>;
  }

  if (isLoading) {
    return <div className="animate-pulse space-y-3">{[...Array(5)].map((_, i) => <div key={i} className="h-8 bg-slate-800 rounded" />)}</div>;
  }

  return (
    <div className="max-w-lg">
      <h2 className="text-lg font-semibold text-white mb-1">Topic Weights</h2>
      <p className="text-sm text-slate-400 mb-4">{user?.display_name} — adjust topic importance (0 = hide, 3 = max boost)</p>
      <div className="space-y-3">
        {TOPICS.map((topic) => {
          const val = weights[topic] ?? 1.0;
          return (
            <div key={topic} className="flex items-center gap-3">
              <span className="text-sm text-slate-300 w-32 truncate">{topic}</span>
              <input
                type="range"
                min={0} max={3} step={0.5}
                value={val}
                onChange={(e) => handleChange(topic, parseFloat(e.target.value))}
                className="flex-1 accent-brand-500"
              />
              <span className="text-xs text-slate-500 font-mono w-8 text-right">{val.toFixed(1)}</span>
            </div>
          );
        })}
      </div>
      {mutation.isError && <p className="text-sm text-red-400 mt-2">Failed to save.</p>}
    </div>
  );
}
