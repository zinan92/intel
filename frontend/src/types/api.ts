// Shared types mirroring the /api/ui/* backend contracts

export interface FeedItem {
  id: number;
  title: string | null;
  source: string;
  source_kind: string;
  url: string | null;
  summary: string;
  relevance_score: number | null;
  priority_score: number;
  momentum_label: "trending" | "rising" | "stable" | "fading";
  tags: string[];
  narrative_tags: string[];
  published_at: string | null;
  collected_at: string | null;
}

export interface RisingTopic {
  topic: string;
  count: number;
  momentum_label: string;
}

export interface SourceHealth {
  source: string;
  count: number;
  last_seen_at: string | null;
  status: "ok" | "stale" | "no_data" | "degraded";
}

export interface TopEvent {
  id: number;
  narrative_tag: string;
  signal_score: number;
  source_count: number;
  article_count: number;
}

export interface FeedContext {
  rising_topics: RisingTopic[];
  source_health: SourceHealth[];
  top_events?: TopEvent[];
}

export interface FeedPage {
  next_cursor: string | null;
}

export interface FeedResponse {
  items: FeedItem[];
  context: FeedContext;
  page: FeedPage;
}

export interface RelatedItem {
  id: number;
  title: string | null;
  source: string;
  url: string | null;
}

export interface ItemDetail {
  id: number;
  title: string | null;
  source: string;
  source_kind: string;
  url: string | null;
  author: string | null;
  content: string | null;
  tags: string[];
  narrative_tags: string[];
  relevance_score: number | null;
  published_at: string | null;
  collected_at: string | null;
  related: RelatedItem[];
}

export interface Topic {
  slug: string;
  label: string;
  count: number;
  momentum_label: string;
}

export interface TopicDetail extends Topic {
  items: FeedItem[];
}

export interface Source {
  name: string;
  kind: string;
  count: number;
  last_seen_at: string | null;
}

export interface SourceDetail extends Source {
  items: FeedItem[];
}

export interface SearchResponse {
  items: FeedItem[];
}
