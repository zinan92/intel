import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

export function TopBar() {
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = q.trim();
    if (trimmed) {
      navigate(`/search?q=${encodeURIComponent(trimmed)}`);
    }
  }

  return (
    <header className="sticky top-0 z-30 bg-slate-950/80 backdrop-blur-md border-b border-surface-border">
      <div className="max-w-screen-xl mx-auto h-14 px-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 group">
          <div className="w-7 h-7 rounded bg-brand-500 flex items-center justify-center">
            <span className="text-slate-950 font-bold text-sm font-mono">P</span>
          </div>
          <span className="text-sm font-semibold text-slate-200 group-hover:text-brand-400 transition-colors tracking-tight">
            Park Intel
          </span>
        </Link>
        <form onSubmit={handleSearch} className="flex items-center">
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search signals..."
            className="w-56 text-sm bg-slate-800/60 border border-surface-border rounded-lg px-3 py-1.5 text-slate-300 placeholder:text-slate-500 focus:outline-none focus:border-brand-500/50 focus:ring-1 focus:ring-brand-500/20 transition-all"
          />
        </form>
      </div>
    </header>
  );
}
