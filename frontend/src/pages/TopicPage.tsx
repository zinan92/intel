import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { FeedCard } from "../components/FeedCard";
import { ItemDrawer } from "../components/ItemDrawer";
import type { FeedItem } from "../types/api";

export function TopicPage() {
  const { slug } = useParams<{ slug: string }>();
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["topic", slug],
    queryFn: () => api.topicDetail(slug!),
    enabled: !!slug,
    staleTime: 30_000,
  });

  return (
    <div className="max-w-2xl">
      <div className="mb-4">
        <Link to="/" className="text-xs text-slate-500 hover:text-slate-300">
          ← Back to feed
        </Link>
        {data && (
          <div className="mt-2">
            <h1 className="text-xl font-semibold text-white">{data.label}</h1>
            <p className="text-sm text-slate-400 mt-0.5">{data.count} articles</p>
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
          Topic not found or API unavailable.
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
