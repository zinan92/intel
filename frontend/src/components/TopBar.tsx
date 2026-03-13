import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";

export function TopBar() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = q.trim();
    if (trimmed) {
      navigate(`/search?q=${encodeURIComponent(trimmed)}`);
    }
  }

  return (
    <header className="sticky top-0 z-30 bg-white border-b border-gray-200 h-14 flex items-center px-4 gap-4">
      <Link to="/" className="font-semibold text-brand-600 text-lg tracking-tight shrink-0">
        Park Intel
      </Link>
      <form onSubmit={handleSearch} className="flex-1 max-w-xl">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search articles..."
          className="w-full h-9 px-3 text-sm border border-gray-300 rounded-md bg-gray-50 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
        />
      </form>
    </header>
  );
}
