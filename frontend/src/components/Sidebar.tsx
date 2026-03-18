import { Link, useLocation, useSearchParams } from "react-router-dom";
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

const USER_OPTIONS = [
  { value: "", label: "Default" },
  { value: "wendy", label: "Wendy" },
  { value: "monica", label: "Monica" },
];

export function Sidebar() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeUser = searchParams.get("user") ?? "";

  const { data: topics } = useQuery({
    queryKey: ["topics"],
    queryFn: () => api.topics(),
    staleTime: 60_000,
  });

  const topTopics = topics?.slice(0, 10) ?? [];

  function isActive(path: string) {
    return location.pathname === path;
  }

  function handleUserChange(value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set("user", value);
    } else {
      next.delete("user");
    }
    setSearchParams(next);
  }

  return (
    <aside className="w-48 shrink-0 hidden lg:block">
      <nav className="sticky top-20 space-y-6 pr-2">
        {/* User selector */}
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">User</p>
          <select
            value={activeUser}
            onChange={(e) => handleUserChange(e.target.value)}
            className="w-full text-sm border border-gray-300 rounded px-2 py-1 text-gray-700 focus:outline-none focus:border-brand-500"
          >
            {USER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          {activeUser && (
            <Link
              to={`/settings?user=${encodeURIComponent(activeUser)}`}
              className="block mt-1.5 text-xs text-brand-600 hover:text-brand-700"
            >
              Settings
            </Link>
          )}
        </div>

        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Feed</p>
          <Link
            to={`/${activeUser ? `?user=${encodeURIComponent(activeUser)}` : ""}`}
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
      </nav>
    </aside>
  );
}
