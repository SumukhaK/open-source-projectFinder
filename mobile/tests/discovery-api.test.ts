import {
  DiscoveryApiError,
  DiscoveryNetworkError,
  DiscoveryResponseError,
  getFavourites,
  getProject,
  removeFavourite,
  saveFavourite,
  searchProjects,
} from '../src/features/discovery/api/discovery';

const project = {
  id: 1,
  name: 'compass',
  full_name: 'octocat/compass',
  owner: 'octocat',
  avatar_url: '',
  description: 'Discover projects',
  stars: 42,
  language: 'Python',
  url: 'https://github.com/octocat/compass',
};
const item = {
  ...project,
  sources: ['github', 'archive'],
  license: 'MIT',
  license_conflict: false,
  matched_section: 'README',
  snippet: 'A compass for projects',
  freshness: 'live+archive',
  rank: 1,
  rrf_score: 0.031,
};
const results = {
  items: [item],
  next_cursor: 'cursor-2',
  has_more: true,
  total: null,
  degraded: false,
  sources: {
    github: { status: 'ok', incomplete: false, reason: null, retry_after: null },
    archive: { status: 'ok', incomplete: false, reason: null, retry_after: null, coverage: 'unknown' },
  },
  archive_as_of: null,
  ranking_version: 'rrf-v1',
  generation: `${'a'.repeat(40)}:rrf-v1`,
};
const response = (status: number, data: object = {}, headers: Record<string, string> = {}) => ({
  ok: status < 400,
  status,
  headers: { get: (name: string) => headers[name] ?? null },
  json: async () => data,
});

afterEach(() => jest.restoreAllMocks());

test('search posts the v1 contract with page_size and a passthrough cursor', async () => {
  const fetcher = jest.spyOn(global, 'fetch').mockResolvedValue(response(200, results) as Response);
  await expect(searchProjects('session', { idea: '  task manager  ', cursor: 'cursor-2' })).resolves.toEqual(results);
  const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
  expect(url).toBe('http://localhost:8000/v1/projects/search');
  expect(init).toEqual(expect.objectContaining({
    method: 'POST',
    headers: expect.objectContaining({ Authorization: 'Bearer session', 'Content-Type': 'application/json' }),
  }));
  const body = JSON.parse(String(init.body));
  expect(body).toEqual({ idea: 'task manager', page_size: 20, cursor: 'cursor-2' });
  expect(Object.keys(body).sort()).toEqual(['cursor', 'idea', 'page_size']);
});

test('page_size stays within the server bound and invalid requests never reach the backend', async () => {
  const fetcher = jest.spyOn(global, 'fetch').mockResolvedValue(response(200, results) as Response);
  await searchProjects('session', { idea: 'task manager', pageSize: 50 });
  const [, init] = fetcher.mock.calls[0] as [string, RequestInit];
  expect(JSON.parse(String(init.body)).page_size).toBe(50);
  await expect(searchProjects('session', { idea: 'task manager', pageSize: 51 })).rejects.toThrow('Invalid search request');
  await expect(searchProjects('session', { idea: 'a' })).rejects.toThrow('Describe your idea');
  expect(fetcher).toHaveBeenCalledTimes(1);
});

test('a legacy or malformed v1 payload is rejected by the response schema', async () => {
  const legacy = {
    items: [project],
    total: 1,
    incomplete: false,
    page: 1,
    per_page: 20,
    sort: 'relevance',
    order: 'desc',
    source: 'github_keywords',
  };
  jest.spyOn(global, 'fetch').mockResolvedValue(response(200, legacy) as Response);
  await expect(searchProjects('session', { idea: 'task manager' })).rejects.toBeInstanceOf(DiscoveryResponseError);

  jest.spyOn(global, 'fetch').mockResolvedValue(response(200, { ...results, total: 1 }) as Response);
  await expect(searchProjects('session', { idea: 'task manager' })).rejects.toBeInstanceOf(DiscoveryResponseError);

  const { next_cursor, ...withoutCursor } = results;
  void next_cursor;
  jest.spyOn(global, 'fetch').mockResolvedValue(response(200, withoutCursor) as Response);
  await expect(searchProjects('session', { idea: 'task manager' })).rejects.toBeInstanceOf(DiscoveryResponseError);

  jest.spyOn(global, 'fetch').mockResolvedValue(
    response(200, { ...results, items: [{ ...item, freshness: 'unknown' }] }) as Response,
  );
  await expect(searchProjects('session', { idea: 'task manager' })).rejects.toBeInstanceOf(DiscoveryResponseError);
});

test.each([
  ['SEARCH_INCOMPLETE', 503, true, /results may be partial/i],
  ['SEARCH_BUSY', 503, true, /busy/i],
  ['SEARCH_TIMEOUT', 503, true, /timed out/i],
  ['SEARCH_UNAVAILABLE', 503, true, /starting or unavailable/i],
  ['CURSOR_EXPIRED', 410, false, /search expired/i],
  ['CURSOR_INVALID', 400, false, /start a new search/i],
  ['UNSUPPORTED_FILTER', 422, false, /unsupported/i],
])('typed %s errors keep their code, retryability and a distinct message', async (code, status, retryable, message) => {
  jest.spyOn(global, 'fetch').mockResolvedValue(
    response(status, { detail: { code, message: 'server text', retryable } }) as Response,
  );
  const failure = await searchProjects('session', { idea: 'task manager' }).catch(error => error);
  expect(failure).toBeInstanceOf(DiscoveryApiError);
  expect(failure.code).toBe(code);
  expect(failure.status).toBe(status);
  expect(failure.retryable).toBe(retryable);
  expect(failure.message).toMatch(message);
});

test('rate limits honour Retry-After and keep the status for the screen', async () => {
  jest.spyOn(global, 'fetch').mockResolvedValue(response(429, {}, { 'Retry-After': '30' }) as Response);
  const failure = await searchProjects('session', { idea: 'task manager' }).catch(error => error);
  expect(failure).toBeInstanceOf(DiscoveryApiError);
  expect(failure.status).toBe(429);
  expect(failure.message).toBe('Too many requests. Try again in 30 seconds.');
});

test('rate limits without Retry-After fall back to a one-minute wait', async () => {
  jest.spyOn(global, 'fetch').mockResolvedValue(response(429) as Response);
  await expect(searchProjects('session', { idea: 'task manager' })).rejects.toThrow(
    'Too many requests. Try again in 60 seconds.',
  );
});

test('a legacy 503 with Retry-After is reported as a rate limit, not a generic outage', async () => {
  jest.spyOn(global, 'fetch').mockResolvedValue(response(503, {}, { 'Retry-After': '45' }) as Response);
  const failure = await getFavourites('session').catch(error => error);
  expect(failure).toBeInstanceOf(DiscoveryApiError);
  expect(failure.status).toBe(503);
  expect(failure.message).toBe('GitHub is rate limited. Try again in 45 seconds.');
});

test('unauthorised responses keep the 401 status', async () => {
  jest.spyOn(global, 'fetch').mockResolvedValue(response(401) as Response);
  const failure = await searchProjects('session', { idea: 'task manager' }).catch(error => error);
  expect(failure).toBeInstanceOf(DiscoveryApiError);
  expect(failure.status).toBe(401);
});

test('network failures are distinct from backend errors', async () => {
  jest.spyOn(global, 'fetch').mockRejectedValue(new TypeError('offline'));
  await expect(getFavourites('session')).rejects.toBeInstanceOf(DiscoveryNetworkError);
});

test('details and favourites stay on the legacy routes and handle 204 deletes', async () => {
  const fetcher = jest
    .spyOn(global, 'fetch')
    .mockResolvedValue(response(200, { ...project, languages: {}, releases: [], readme: '', readme_truncated: false, contributors: [] }) as Response);
  await getProject('session', 'owner/name');
  expect(fetcher).toHaveBeenLastCalledWith(
    'http://localhost:8000/projects/owner/name',
    expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer session' }) }),
  );
  await saveFavourite('session', 'owner/name');
  expect(fetcher).toHaveBeenLastCalledWith(
    'http://localhost:8000/favourites/owner/name',
    expect.objectContaining({ method: 'PUT' }),
  );
  fetcher.mockResolvedValue(response(204) as Response);
  await expect(removeFavourite('session', 'owner/name')).resolves.toBeUndefined();
  expect(fetcher).toHaveBeenLastCalledWith(
    'http://localhost:8000/favourites/owner/name',
    expect.objectContaining({ method: 'DELETE' }),
  );
});

test('favourite lists and details reject malformed payloads', async () => {
  jest.spyOn(global, 'fetch').mockResolvedValue(response(200, { items: [{ ...project, id: 'one' }] }) as Response);
  await expect(getFavourites('session')).rejects.toBeInstanceOf(DiscoveryResponseError);
  jest.spyOn(global, 'fetch').mockResolvedValue(response(200, { ...project, contributors: 'nope' }) as Response);
  await expect(getProject('session', 'octocat/compass')).rejects.toBeInstanceOf(DiscoveryResponseError);
});

test.each([
  [404, 'This public repository is no longer available.'],
  [409, 'Favourite limit reached. Remove a saved project first.'],
  [422, 'Use a few specific project keywords.'],
  [503, 'GitHub is temporarily unavailable. Try again later.'],
])('legacy backend status %s maps to a user-facing message', async (status, message) => {
  jest.spyOn(global, 'fetch').mockResolvedValue(response(status) as Response);
  await expect(getFavourites('session')).rejects.toThrow(message);
});

test('invalid repository paths are rejected before a request', () => {
  expect(() => getProject('session', 'owner')).toThrow('Invalid repository name');
  expect(() => saveFavourite('session', 'owner/name/extra')).toThrow('Invalid repository name');
});
