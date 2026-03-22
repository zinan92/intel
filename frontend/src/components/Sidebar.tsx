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
            className={`flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-colors ${
              isActive("/") ? "bg-slate-800/60 text-brand-400 font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {isActive("/") && <span className="w-1 h-1 rounded-full bg-brand-400" />}
            Today
          </Link>
          <Link
            to={`/explore${activeUser ? `?user=${encodeURIComponent(activeUser)}` : ""}`}
            className={`flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-colors ${
              isActive("/explore") ? "bg-slate-800/60 text-brand-400 font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {isActive("/explore") && <span className="w-1 h-1 rounded-full bg-brand-400" />}
            Explore
          </Link>
          <Link
            to="/search"
            className={`flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-colors ${
              isActive("/search") ? "bg-slate-800/60 text-brand-400 font-medium" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {isActive("/search") && <span className="w-1 h-1 rounded-full bg-brand-400" />}
            Search
          </Link>
          {activeUser && (
            <Link
              to={`/settings?user=${encodeURIComponent(activeUser)}`}
              className={`flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-colors ${
                isActive("/settings") ? "bg-slate-800/60 text-brand-400 font-medium" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {isActive("/settings") && <span className="w-1 h-1 rounded-full bg-brand-400" />}
              Settings
            </Link>
          )}
        </div>
      </nav>
    </aside>
  );
}
