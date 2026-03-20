import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { stripHtml } from "./FeedCard";

interface Props {
  itemId: number | null;
  onClose: () => void;
}

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const utcIso = iso.endsWith("Z") ? iso : iso + "Z";
  return new Date(utcIso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ItemDrawer({ itemId, onClose }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["item", itemId],
    queryFn: () => api.item(itemId!),
    enabled: itemId !== null,
    staleTime: 60_000,
  });

  return (
    <Dialog.Root open={itemId !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/60 z-40 animate-in fade-in" />
        <Dialog.Content
          className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-2xl bg-slate-900 border-l border-surface-border shadow-xl flex flex-col animate-in slide-in-from-right"
          aria-describedby={undefined}
        >
          <div className="flex items-center justify-between px-5 py-4 border-b border-surface-border shrink-0">
            <Dialog.Title className="text-sm font-semibold text-slate-100 truncate pr-4">
              {data?.title ?? "Article detail"}
            </Dialog.Title>
            <Dialog.Close
              onClick={onClose}
              className="text-slate-400 hover:text-slate-200 text-xl leading-none shrink-0"
              aria-label="Close"
            >
              ✕
            </Dialog.Close>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {isLoading && (
              <div className="space-y-3 animate-pulse">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="h-4 bg-slate-800 rounded" />
                ))}
              </div>
            )}

            {data && (
              <div className="space-y-5">
                {/* Meta row */}
                <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                  <span className="bg-slate-800 px-2 py-0.5 rounded">{data.source}</span>
                  <span className="bg-slate-800 px-2 py-0.5 rounded">{data.source_kind}</span>
                  {data.author && <span>by {data.author}</span>}
                  {data.published_at && <span>{formatDate(data.published_at)}</span>}
                  {data.relevance_score != null && (
                    <span className="ml-auto font-medium text-slate-300">rel {data.relevance_score}/5</span>
                  )}
                </div>

                {/* URL */}
                {data.url && (
                  <a
                    href={data.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-xs text-brand-400 hover:text-brand-300 truncate"
                  >
                    {data.url}
                  </a>
                )}

                {/* Tags */}
                {(data.narrative_tags.length > 0 || data.tags.length > 0) && (
                  <div className="flex flex-wrap gap-1">
                    {data.narrative_tags.map((t) => (
                      <span key={t} className="text-xs bg-brand-500/10 text-brand-400 px-1.5 py-0.5 rounded">
                        {t}
                      </span>
                    ))}
                    {data.tags.map((t) => (
                      <span key={t} className="text-xs bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded">
                        {t}
                      </span>
                    ))}
                  </div>
                )}

                {/* Content */}
                {data.content && (
                  <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap border-t border-surface-border pt-4">
                    {stripHtml(data.content)}
                  </div>
                )}

                {/* Related */}
                {data.related.length > 0 && (
                  <div className="border-t border-surface-border pt-4">
                    <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono mb-2">
                      Related
                    </p>
                    <ul className="space-y-2">
                      {data.related.map((r) => (
                        <li key={r.id}>
                          <a
                            href={r.url ?? "#"}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-slate-200 hover:text-brand-400 leading-snug line-clamp-2"
                          >
                            {r.title ?? "(no title)"}
                            <span className="text-xs text-slate-500 ml-1">{r.source}</span>
                          </a>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
