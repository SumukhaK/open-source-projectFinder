import { z } from 'zod';
import { discoveryConfig } from '../../../config/discovery';

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
};
export type ProjectDetails = Project & {
  languages: Record<string, number>;
  releases: { name: string; tag: string; published_at: string | null }[];
  readme: string;
  readme_truncated: boolean;
  contributors: { login: string; avatar_url: string; contributions: number }[];
};
export type SearchResults = {
  items: Project[];
  total: number;
  incomplete: boolean;
  page: number;
  per_page: number;
  sort: string;
  order: string;
  source: string;
};
export type SearchInput = {
  idea: string;
  page?: number;
  perPage?: number;
  sort?: 'stars' | 'forks' | 'updated';
  order?: 'asc' | 'desc';
};

export class DiscoveryApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
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
export const searchResultsSchema = z.object({
  items: z.array(projectSchema),
  total: z.number().int(),
  incomplete: z.boolean(),
  page: z.number().int(),
  per_page: z.number().int(),
  sort: z.string(),
  order: z.string(),
  source: z.string(),
});
const favouritesSchema = z.object({ items: z.array(projectSchema) });
const searchRequestSchema = z.object({
  idea: z.string().trim().min(discoveryConfig.minIdeaLength, 'Describe your idea').max(discoveryConfig.maxIdeaLength, 'Describe your idea'),
  page: z.number().int().min(1, 'Invalid search request').max(discoveryConfig.maxPage, 'Invalid search request'),
  per_page: z.number().int().min(1, 'Invalid search request').max(100, 'Invalid search request').optional(),
  sort: z.enum(['stars', 'forks', 'updated']).optional(),
  order: z.enum(['asc', 'desc']).optional(),
});

function apiError(response: Response): DiscoveryApiError {
  const retryAfter = response.headers.get('Retry-After') ?? '60';
  const message = response.status === 429
    ? `Too many requests. Try again in ${retryAfter} seconds.`
    : response.status === 401
      ? 'Your session expired. Sign in again.'
      : response.status === 404
        ? 'This public repository is no longer available.'
        : response.status === 409
          ? 'Favourite limit reached. Remove a saved project first.'
          : response.status === 422
            ? 'Use a few specific project keywords.'
            : 'GitHub is temporarily unavailable. Try again later.';
  return new DiscoveryApiError(message, response.status);
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
    if (!response.ok) throw apiError(response);
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
  const parsed = searchRequestSchema.safeParse({
    idea: input.idea.trim(),
    page: input.page ?? 1,
    per_page: input.perPage,
    sort: input.sort,
    order: input.order,
  });
  if (!parsed.success) throw new Error(parsed.error.issues[0]?.message ?? 'Invalid search request');
  return request(token, '/projects/search', searchResultsSchema, {
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
