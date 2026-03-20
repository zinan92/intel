import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

function MomentumDot({ label }: { label: string }) {
  const color =
    label === "rising" || label === "trending"
      ? "bg-green-400"
      : label === "stable"
      ? "bg-slate-500"
      : "bg-red-400";
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
          <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">User</p>
          <select
            value={activeUser}
            onChange={(e) => handleUserChange(e.target.value)}
            className="w-full text-sm bg-slate-800 border border-surface-border rounded px-2 py-1 text-slate-300 focus:outline-none focus:border-brand-500"
          >
            {USER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          {activeUser && (
            <Link
              to={`/settings?user=${encodeURIComponent(activeUser)}`}
              className="block mt-1.5 text-xs text-slate-500 hover:text-brand-400"
            >
              Settings
            </Link>
          )}
        </div>

        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">Feed</p>
          <Link
            to={`/${activeUser ? `?user=${encodeURIComponent(activeUser)}` : ""}`}
            className={`block px-2 py-1 rounded text-sm ${
              isActive("/") ? "bg-slate-800/60 text-brand-400 font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            All
          </Link>
          <Link
            to="/events/history"
            className={`block px-2 py-1 rounded text-sm ${
              isActive("/events/history") ? "bg-slate-800/60 text-brand-400 font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            History
          </Link>
          <Link
            to="/constellation"
            className={`block px-2 py-1 rounded text-sm ${
              isActive("/constellation") ? "bg-slate-800/60 text-brand-400 font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Constellation
          </Link>
        </div>

        {topTopics.length > 0 && (
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">Topics</p>
            <ul className="space-y-0.5">
              {topTopics.map((t) => (
                <li key={t.slug}>
                  <Link
                    to={`/topics/${t.slug}`}
                    className={`flex items-center gap-2 px-2 py-1 rounded text-sm ${
                      isActive(`/topics/${t.slug}`)
                        ? "bg-slate-800/60 text-brand-400 font-medium"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    <MomentumDot label={t.momentum_label} />
                    <span className="truncate">{t.label}</span>
                    <span className="ml-auto text-xs text-slate-500 font-mono">{t.count}</span>
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
