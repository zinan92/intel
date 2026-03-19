import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { FeedCard } from "../components/FeedCard";
import { ItemDrawer } from "../components/ItemDrawer";
import type { FeedItem } from "../types/api";

function formatDate(iso: string | null): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SourcePage() {
  const { name } = useParams<{ name: string }>();
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["source", name],
    queryFn: () => api.sourceDetail(name!),
    enabled: !!name,
    staleTime: 30_000,
  });

  return (
    <div className="max-w-2xl">
      <div className="mb-4">
        <Link to="/" className="text-xs text-slate-500 hover:text-slate-300">
          ← Back to feed
        </Link>
        {data && (
          <div className="mt-2 flex items-baseline gap-3">
            <h1 className="text-xl font-semibold text-white">{data.name}</h1>
            <span className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded">{data.kind}</span>
            <span className="text-sm text-slate-500 ml-auto">{data.count} articles · last {formatDate(data.last_seen_at)}</span>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 bg-slate-800 rounded-lg animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <div className="text-sm text-red-400 bg-red-500/10 px-4 py-3 rounded-lg">
          Source not found or API unavailable.
        </div>
      )}

      <div className="space-y-2">
        {data?.items.map((item) => (
          <FeedCard key={item.id} item={item} onClick={(i: FeedItem) => setSelectedId(i.id)} />
        ))}
      </div>

      <ItemDrawer itemId={selectedId} onClose={() => setSelectedId(null)} />
    </div>
  );
}
