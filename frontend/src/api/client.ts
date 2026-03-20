import type {
  FeedResponse,
  ItemDetail,
  EventDetail,
  EventHistoryResponse,
  ScorecardResponse,
  Topic,
  TopicDetail,
  Source,
  SourceDetail,
  SearchResponse,
  UserProfile,
} from "../types/api";

const BASE = import.meta.env.VITE_API_URL ?? "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${path}`);
  }
  return res.json() as Promise<T>;
}

export interface FeedParams {
  source?: string;
  topic?: string;
  events_only?: boolean;
  window?: string;
  limit?: number;
  cursor?: string;
  user?: string;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const pairs: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") {
      pairs.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
    }
  }
  return pairs.length ? `?${pairs.join("&")}` : "";
}

export const api = {
  feed: (params: FeedParams = {}): Promise<FeedResponse> =>
    get(`/api/ui/feed${buildQuery(params as Record<string, string | number | undefined>)}`),

  item: (id: number): Promise<ItemDetail> =>
    get(`/api/ui/items/${id}`),

  topics: (window = "24h"): Promise<Topic[]> =>
    get(`/api/ui/topics${buildQuery({ window })}`),

  topicDetail: (slug: string): Promise<TopicDetail> =>
    get(`/api/ui/topics/${encodeURIComponent(slug)}`),

  sources: (): Promise<Source[]> =>
    get("/api/ui/sources"),

  sourceDetail: (name: string): Promise<SourceDetail> =>
    get(`/api/ui/sources/${encodeURIComponent(name)}`),

  search: (q: string, limit = 20): Promise<SearchResponse> =>
    get(`/api/ui/search${buildQuery({ q, limit })}`),

  users: (): Promise<UserProfile[]> =>
    get("/api/users"),

  user: (username: string): Promise<UserProfile> =>
    get(`/api/users/${encodeURIComponent(username)}`),

  eventDetail: (id: number): Promise<EventDetail> =>
    get(`/api/events/${id}`),

  eventHistory: (params: { days?: number; tag?: string; limit?: number } = {}): Promise<EventHistoryResponse> =>
    get(`/api/events/history${buildQuery(params as Record<string, string | number | undefined>)}`),

  scorecard: (params: { days?: number; min_events?: number } = {}): Promise<ScorecardResponse> =>
    get(`/api/events/scorecard${buildQuery(params as Record<string, string | number | undefined>)}`),

  updateWeights: async (username: string, weights: Record<string, number>): Promise<UserProfile> => {
    const res = await fetch(`${BASE}/api/users/${encodeURIComponent(username)}/weights`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ weights }),
    });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  },
};
