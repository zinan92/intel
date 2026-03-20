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
  sources: string[];
  tickers: string[];
  narrative_summary: string | null;
  prev_signal_score: number | null;
}

export interface EventArticle {
  id: number;
  title: string | null;
  source: string;
  url: string | null;
  relevance_score: number | null;
  summary: string;
  published_at: string | null;
  collected_at: string | null;
}

export interface PriceImpact {
  ticker: string;
  price_at_event: number;
  change_1d: number;
  change_3d: number;
  change_5d: number;
}

export interface EventInfo {
  id: number;
  narrative_tag: string;
  source_count: number;
  article_count: number;
  signal_score: number;
  avg_relevance: number;
  window_start: string | null;
  window_end: string | null;
  status: string;
  narrative_summary: string | null;
  prev_signal_score: number | null;
  trading_play: string | null;
}

export interface ScorecardBucket {
  label: string;
  min_score: number;
  event_count: number;
  avg_change_1d: number;
  avg_change_3d: number;
  avg_change_5d: number;
}

export interface ScorecardResponse {
  buckets: ScorecardBucket[];
  total_events_with_data: number;
  period_days: number;
}

export interface EventDetail {
  event: EventInfo;
  articles: EventArticle[];
  price_impacts: PriceImpact[];
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

export interface EventHistoryItem {
  id: number;
  narrative_tag: string;
  signal_score: number;
  source_count: number;
  article_count: number;
  narrative_summary: string | null;
  window_start: string | null;
  window_end: string | null;
  status: string;
  tickers: string[];
}

export interface EventHistoryResponse {
  events: EventHistoryItem[];
}

export interface UserProfile {
  username: string;
  display_name: string;
  topic_weights: Record<string, number>;
  created_at: string | null;
}
