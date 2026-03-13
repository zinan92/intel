import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

interface Props {
  itemId: number | null;
  onClose: () => void;
}

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, {
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
        <Dialog.Overlay className="fixed inset-0 bg-black/30 z-40 animate-in fade-in" />
        <Dialog.Content
          className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-2xl bg-white shadow-xl flex flex-col animate-in slide-in-from-right"
          aria-describedby={undefined}
        >
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
            <Dialog.Title className="text-sm font-semibold text-gray-700 truncate pr-4">
              {data?.title ?? "Article detail"}
            </Dialog.Title>
            <Dialog.Close
              onClick={onClose}
              className="text-gray-400 hover:text-gray-700 text-xl leading-none shrink-0"
              aria-label="Close"
            >
              ✕
            </Dialog.Close>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {isLoading && (
              <div className="space-y-3 animate-pulse">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="h-4 bg-gray-100 rounded" />
                ))}
              </div>
            )}

            {data && (
              <div className="space-y-5">
                {/* Meta row */}
                <div className="flex flex-wrap gap-2 text-xs text-gray-500">
                  <span className="bg-gray-100 px-2 py-0.5 rounded">{data.source}</span>
                  <span className="bg-gray-100 px-2 py-0.5 rounded">{data.source_kind}</span>
                  {data.author && <span>by {data.author}</span>}
                  {data.published_at && <span>{formatDate(data.published_at)}</span>}
                  {data.relevance_score != null && (
                    <span className="ml-auto font-medium text-gray-700">rel {data.relevance_score}/5</span>
                  )}
                </div>

                {/* URL */}
                {data.url && (
                  <a
                    href={data.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-xs text-brand-600 hover:underline truncate"
                  >
                    {data.url}
                  </a>
                )}

                {/* Tags */}
                {(data.narrative_tags.length > 0 || data.tags.length > 0) && (
                  <div className="flex flex-wrap gap-1">
                    {data.narrative_tags.map((t) => (
                      <span key={t} className="text-xs bg-brand-50 text-brand-600 px-1.5 py-0.5 rounded">
                        {t}
                      </span>
                    ))}
                    {data.tags.map((t) => (
                      <span key={t} className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                        {t}
                      </span>
                    ))}
                  </div>
                )}

                {/* Content */}
                {data.content && (
                  <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap border-t border-gray-100 pt-4">
                    {data.content}
                  </div>
                )}

                {/* Related */}
                {data.related.length > 0 && (
                  <div className="border-t border-gray-100 pt-4">
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                      Related
                    </p>
                    <ul className="space-y-2">
                      {data.related.map((r) => (
                        <li key={r.id}>
                          <a
                            href={r.url ?? "#"}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-gray-700 hover:text-brand-600 leading-snug line-clamp-2"
                          >
                            {r.title ?? "(no title)"}
                            <span className="text-xs text-gray-400 ml-1">{r.source}</span>
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
