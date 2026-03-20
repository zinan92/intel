import { Link, useLocation, useSearchParams } from "react-router-dom";

const USER_OPTIONS = [
  { value: "", label: "Default" },
  { value: "wendy", label: "Wendy" },
  { value: "monica", label: "Monica" },
];

export function Sidebar() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeUser = searchParams.get("user") ?? "";

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
        </div>

        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">Nav</p>
          <Link
            to={`/${activeUser ? `?user=${encodeURIComponent(activeUser)}` : ""}`}
            className={`block px-2 py-1 rounded text-sm ${
              isActive("/") ? "bg-slate-800/60 text-brand-400 font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Signals
          </Link>
          <Link
            to={`/browse${activeUser ? `?user=${encodeURIComponent(activeUser)}` : ""}`}
            className={`block px-2 py-1 rounded text-sm ${
              isActive("/browse") ? "bg-slate-800/60 text-brand-400 font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Browse
          </Link>
          <Link
            to="/search"
            className={`block px-2 py-1 rounded text-sm ${
              isActive("/search") ? "bg-slate-800/60 text-brand-400 font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Search
          </Link>
          {activeUser && (
            <Link
              to={`/settings?user=${encodeURIComponent(activeUser)}`}
              className={`block px-2 py-1 rounded text-sm ${
                isActive("/settings") ? "bg-slate-800/60 text-brand-400 font-medium" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Settings
            </Link>
          )}
        </div>
      </nav>
    </aside>
  );
}
