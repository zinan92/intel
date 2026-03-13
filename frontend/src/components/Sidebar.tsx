import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

function MomentumDot({ label }: { label: string }) {
  const color =
    label === "rising" || label === "trending"
      ? "bg-green-400"
      : label === "stable"
      ? "bg-gray-300"
      : "bg-red-300";
  return <span className={`inline-block w-1.5 h-1.5 rounded-full ${color} shrink-0`} />;
}

export function Sidebar() {
  const location = useLocation();

  const { data: topics } = useQuery({
    queryKey: ["topics"],
    queryFn: () => api.topics(),
    staleTime: 60_000,
  });

  const { data: sources } = useQuery({
    queryKey: ["sources"],
    queryFn: () => api.sources(),
    staleTime: 60_000,
  });

  const topTopics = topics?.slice(0, 10) ?? [];
  const topSources = sources?.slice(0, 8) ?? [];

  function isActive(path: string) {
    return location.pathname === path;
  }

  return (
    <aside className="w-48 shrink-0 hidden lg:block">
      <nav className="sticky top-20 space-y-6 pr-2">
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Feed</p>
          <Link
            to="/"
            className={`block px-2 py-1 rounded text-sm ${
              isActive("/") ? "bg-brand-50 text-brand-700 font-medium" : "text-gray-600 hover:text-gray-900"
            }`}
          >
            All
          </Link>
        </div>

        {topTopics.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Topics</p>
            <ul className="space-y-0.5">
              {topTopics.map((t) => (
                <li key={t.slug}>
                  <Link
                    to={`/topics/${t.slug}`}
                    className={`flex items-center gap-2 px-2 py-1 rounded text-sm ${
                      isActive(`/topics/${t.slug}`)
                        ? "bg-brand-50 text-brand-700 font-medium"
                        : "text-gray-600 hover:text-gray-900"
                    }`}
                  >
                    <MomentumDot label={t.momentum_label} />
                    <span className="truncate">{t.label}</span>
                    <span className="ml-auto text-xs text-gray-400">{t.count}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}

        {topSources.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Sources</p>
            <ul className="space-y-0.5">
              {topSources.map((s) => (
                <li key={s.name}>
                  <Link
                    to={`/sources/${s.name}`}
                    className={`flex items-center gap-2 px-2 py-1 rounded text-sm ${
                      isActive(`/sources/${s.name}`)
                        ? "bg-brand-50 text-brand-700 font-medium"
                        : "text-gray-600 hover:text-gray-900"
                    }`}
                  >
                    <span className="truncate">{s.name}</span>
                    <span className="ml-auto text-xs text-gray-400">{s.count}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </nav>
    </aside>
  );
}
