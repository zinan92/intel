import { Routes, Route } from "react-router-dom";
import { TopBar } from "./components/TopBar";
import { Sidebar } from "./components/Sidebar";
import { FeedPage } from "./pages/FeedPage";
import { TopicPage } from "./pages/TopicPage";
import { SourcePage } from "./pages/SourcePage";
import { SearchPage } from "./pages/SearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { EventPage } from "./pages/EventPage";

export function App() {
  return (
    <div className="min-h-screen bg-gray-50 font-sans">
      <TopBar />
      <div className="max-w-screen-xl mx-auto px-4 py-5 flex gap-6">
        <Sidebar />
        <main className="flex-1 min-w-0">
          <Routes>
            <Route path="/" element={<FeedPage />} />
            <Route path="/events/:id" element={<EventPage />} />
            <Route path="/topics/:slug" element={<TopicPage />} />
            <Route path="/sources/:name" element={<SourcePage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
