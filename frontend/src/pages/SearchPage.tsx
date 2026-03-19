import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { FeedCard } from "../components/FeedCard";
import { ItemDrawer } from "../components/ItemDrawer";
import type { FeedItem } from "../types/api";

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQ = searchParams.get("q") ?? "";
  const [inputValue, setInputValue] = useState(initialQ);
  const [query, setQuery] = useState(initialQ);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Sync URL → input when navigating back/forward
  useEffect(() => {
    const q = searchParams.get("q") ?? "";
    setInputValue(q);
    setQuery(q);
  }, [searchParams]);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["search", query],
    queryFn: () => api.search(query),
    enabled: query.trim().length > 0,
    staleTime: 15_000,
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = inputValue.trim();
    if (trimmed) {
      setQuery(trimmed);
      setSearchParams({ q: trimmed });
    }
  }

  const items = data?.items ?? [];

  return (
    <div className="max-w-2xl">
      <form onSubmit={handleSubmit} className="mb-5">
        <div className="flex gap-2">
          <input
            type="search"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Search articles..."
            autoFocus
            className="flex-1 h-10 px-3 text-sm bg-slate-800 border border-surface-border text-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-brand-500/50 focus:border-brand-500/50"
          />
          <button
            type="submit"
            className="px-4 h-10 text-sm bg-brand-500 text-slate-950 rounded-lg hover:bg-brand-400 transition-colors font-medium"
          >
            Search
          </button>
        </div>
      </form>

      {query && (
        <p className="text-xs text-slate-500 mb-3">
          {isFetching ? "Searching..." : `${items.length} result${items.length !== 1 ? "s" : ""} for "${query}"`}
        </p>
      )}

      {isLoading && (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-28 bg-slate-800 rounded-lg animate-pulse" />
          ))}
        </div>
      )}

      {!isLoading && query && items.length === 0 && (
        <div className="text-sm text-slate-500 text-center py-12">
          No results found.
        </div>
      )}

      <div className="space-y-2">
        {items.map((item) => (
          <FeedCard key={item.id} item={item} onClick={(i: FeedItem) => setSelectedId(i.id)} />
        ))}
      </div>

      <ItemDrawer itemId={selectedId} onClose={() => setSelectedId(null)} />
    </div>
  );
}
