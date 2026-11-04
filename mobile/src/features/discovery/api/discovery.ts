import { z } from 'zod';
import { discoveryConfig } from '../../../config/discovery';

export type SearchSource = 'github' | 'archive';
export type SearchFreshness = 'live' | 'archive' | 'live+archive';
export type Project = {
  id: number;
  name: string;
  full_name: string;
  owner: string;
  avatar_url: string;
  description: string;
  stars: number;
  language: string | null;
  url: string;
  license?: string | null;
  sources?: SearchSource[];
  license_conflict?: boolean;
  matched_section?: string | null;
  snippet?: string | null;
  freshness?: SearchFreshness;
  rank?: number;
  rrf_score?: number;
};
export type ProjectDetails = Project & {
  languages: Record<string, number>;
  releases: { name: string; tag: string; published_at: string | null }[];
  readme: string;
  readme_truncated: boolean;
  contributors: { login: string; avatar_url: string; contributions: number }[];
};
export type SearchItem = Project & {
  sources: SearchSource[];
  license: string | null;
  license_conflict: boolean;
  matched_section: string | null;
  snippet: string | null;
  freshness: SearchFreshness;
  rank: number;
  rrf_score: number;
};
export type SourceHealth = {
  status: string;
  incomplete: boolean;
  reason: string | null;
  retry_after: number | null;
};
export type SearchResults = {
  items: SearchItem[];
  next_cursor: string | null;
  has_more: boolean;
  total: null;
  degraded: boolean;
  sources: { github: SourceHealth; archive: SourceHealth & { coverage: string } };
  archive_as_of: string | null;
  ranking_version: string;
  generation: string;
};
export type SearchFilters = { language?: string; license?: string };
export type SearchInput = {
  idea: string;
  cursor?: string;
  pageSize?: number;
  filters?: SearchFilters;
};

export class DiscoveryApiError extends Error {
  constructor(message: string, public status: number, public code?: string, public retryable = false) { super(message); }
}
export class DiscoveryNetworkError extends Error {}
export class DiscoveryResponseError extends Error {}

export const projectSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  full_name: z.string(),
  owner: z.string(),
  avatar_url: z.string(),
  description: z.string(),
  stars: z.number().int(),
  language: z.string().nullable(),
  url: z.string(),
  license: z.string().nullable().optional(),
});
const detailsSchema = projectSchema.extend({
  languages: z.record(z.string(), z.number()),
  releases: z.array(z.object({
    name: z.string(),
    tag: z.string(),
    published_at: z.string().nullable(),
  })),
  readme: z.string(),
  readme_truncated: z.boolean(),
  contributors: z.array(z.object({
    login: z.string(),
    avatar_url: z.string(),
    contributions: z.number().int(),
  })),
});
const sourceHealthSchema = z.object({
  status: z.string(),
  incomplete: z.boolean(),
  reason: z.string().nullable(),
  retry_after: z.number().nullable(),
});
const searchItemSchema = projectSchema.extend({
  sources: z.array(z.enum(['github', 'archive'])),
  license: z.string().nullable(),
  license_conflict: z.boolean(),
  matched_section: z.string().nullable(),
  snippet: z.string().nullable(),
  freshness: z.enum(['live', 'archive', 'live+archive']),
  rank: z.number(),
  rrf_score: z.number(),
});
export const searchResultsSchema = z.object({
  items: z.array(searchItemSchema),
  next_cursor: z.string().nullable(),
  has_more: z.boolean(),
  // v1 has no total count; a number here means the payload is not v1.
  total: z.null(),
  degraded: z.boolean(),
  sources: z.object({ github: sourceHealthSchema, archive: sourceHealthSchema.extend({ coverage: z.string() }) }),
  archive_as_of: z.string().nullable(),
  ranking_version: z.string(),
  generation: z.string(),
});
const favouritesSchema = z.object({ items: z.array(projectSchema) });
const searchRequestSchema = z.strictObject({
  idea: z.string().trim().min(discoveryConfig.minIdeaLength, 'Describe your idea').max(discoveryConfig.maxIdeaLength, 'Describe your idea'),
  page_size: z.number().int().min(1, 'Invalid search request').max(discoveryConfig.maxPageSize, 'Invalid search request').optional(),
  cursor: z.string().min(1, 'Invalid search request').max(2048, 'Invalid search request').optional(),
  filters: z.strictObject({
    language: z.string().min(1, 'Invalid search request').max(64, 'Invalid search request').optional(),
    license: z.string().min(1, 'Invalid search request').max(64, 'Invalid search request').optional(),
  }).optional(),
});

function apiError(response: Response, body: unknown): DiscoveryApiError {
  const retryAfter = response.headers.get('Retry-After');
  // FastAPI wraps typed errors in {"detail": {code, message, retryable}}; legacy
  // routes use a plain string detail.
  const inner = body && typeof body === 'object' && 'detail' in body ? (body as { detail?: unknown }).detail : body;
  const envelope = inner && typeof inner === 'object' && 'code' in inner
    ? (inner as { code?: unknown; message?: unknown; retryable?: unknown })
    : undefined;
  const code = typeof envelope?.code === 'string' ? envelope.code : undefined;
  const retryable = envelope?.retryable === true;
  const serverMessage = typeof envelope?.message === 'string' ? envelope.message : '';
  const message = typedMessage(code)
    ?? (response.status === 429
      ? `Too many requests. Try again in ${retryAfter ?? '60'} seconds.`
      : response.status === 401
        ? 'Your session expired. Sign in again.'
        : response.status === 404
          ? 'This public repository is no longer available.'
          : response.status === 409
            ? 'Favourite limit reached. Remove a saved project first.'
            : response.status === 422
              ? 'Use a few specific project keywords.'
              : response.status === 503 && retryAfter
                ? `GitHub is rate limited. Try again in ${retryAfter} seconds.`
                : serverMessage || 'GitHub is temporarily unavailable. Try again later.');
  return new DiscoveryApiError(message, response.status, code, retryable);
}

function typedMessage(code: string | undefined): string | undefined {
  switch (code) {
    case 'SEARCH_INCOMPLETE': return 'Results may be partial. Try again in a moment.';
    case 'SEARCH_BUSY': return 'Search is busy. Try again shortly.';
    case 'SEARCH_TIMEOUT': return 'Search timed out. Try again.';
    case 'SEARCH_UNAVAILABLE': return 'Search is starting or unavailable. Try again shortly.';
    case 'CURSOR_EXPIRED': return 'This search expired. Start a new search.';
    case 'CURSOR_INVALID': return 'Start a new search.';
    case 'UNSUPPORTED_FILTER': return 'Unsupported language or licence filter.';
    case 'INVALID_REQUEST': return 'Use a few specific project keywords.';
    default: return undefined;
  }
}

async function request<T>(token: string, path: string, schema: z.ZodType<T> | undefined, init: RequestInit = {}): Promise<T> {
  if (!__DEV__ && new URL(discoveryConfig.apiUrl).protocol !== 'https:') throw new Error('A secure backend connection is required.');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), discoveryConfig.timeoutMs);
  try {
    const response = await fetch(discoveryConfig.apiUrl.replace(/\/$/, '') + path, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...init.headers },
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => undefined);
      throw apiError(response, detail);
    }
    if (response.status === 204) return undefined as T;
    const payload: unknown = await response.json();
    const parsed = schema ? schema.safeParse(payload) : { success: true as const, data: payload as T };
    if (!parsed.success) throw new DiscoveryResponseError('Unexpected response from the server.');
    return parsed.data;
  } catch (error) {
    if (error instanceof DiscoveryApiError || error instanceof DiscoveryResponseError) throw error;
    throw new DiscoveryNetworkError('Unable to connect. Check your connection and try again.');
  } finally {
    clearTimeout(timeout);
  }
}

const repositoryPath = (fullName: string) => {
  const parts = fullName.split('/');
  if (parts.length !== 2 || parts.some(part => !part)) throw new Error('Invalid repository name');
  return parts.map(encodeURIComponent).join('/');
};

export async function searchProjects(token: string, input: SearchInput): Promise<SearchResults> {
  const body: Record<string, unknown> = {
    idea: input.idea.trim(),
    page_size: input.pageSize ?? discoveryConfig.pageSize,
  };
  if (input.cursor !== undefined) body.cursor = input.cursor;
  if (input.filters !== undefined) {
    body.filters = {
      ...(input.filters.language !== undefined ? { language: input.filters.language } : {}),
      ...(input.filters.license !== undefined ? { license: input.filters.license } : {}),
    };
  }
  const parsed = searchRequestSchema.safeParse(body);
  if (!parsed.success) throw new Error(parsed.error.issues[0]?.message ?? 'Invalid search request');
  return request(token, '/v1/projects/search', searchResultsSchema, {
    method: 'POST',
    body: JSON.stringify(parsed.data),
  });
}
export const getProject = (token: string, fullName: string) =>
  request(token, '/projects/' + repositoryPath(fullName), detailsSchema);
export const getFavourites = (token: string) =>
  request(token, '/favourites', favouritesSchema);
export const saveFavourite = (token: string, fullName: string) =>
  request(token, '/favourites/' + repositoryPath(fullName), projectSchema, { method: 'PUT' });
export const removeFavourite = (token: string, fullName: string) =>
  request<void>(token, '/favourites/' + repositoryPath(fullName), undefined, { method: 'DELETE' });
