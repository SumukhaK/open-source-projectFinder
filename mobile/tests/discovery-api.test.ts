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
const results = {
  items: [project],
  total: 1,
  incomplete: false,
  page: 1,
  per_page: 20,
  sort: 'relevance',
  order: 'desc',
  source: 'github_keywords',
};
const response = (status: number, data: object = {}, headers: Record<string, string> = {}) => ({
  ok: status < 400,
  status,
  headers: { get: (name: string) => headers[name] ?? null },
  json: async () => data,
});

afterEach(() => jest.restoreAllMocks());

test('search sends the merged contract, bearer token and page through the single transport', async () => {
  const fetcher = jest.spyOn(global, 'fetch').mockResolvedValue(response(200, results) as Response);
  await expect(searchProjects('session', { idea: '  task manager  ', page: 2 })).resolves.toEqual(results);
  expect(fetcher).toHaveBeenCalledWith(
    'http://localhost:8000/projects/search',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ idea: 'task manager', page: 2 }),
      headers: expect.objectContaining({ Authorization: 'Bearer session', 'Content-Type': 'application/json' }),
    }),
  );
});

test('search rejects invalid requests before calling the backend', async () => {
  const fetcher = jest.spyOn(global, 'fetch');
  await expect(searchProjects('session', { idea: 'a' })).rejects.toThrow('Describe your idea');
  await expect(searchProjects('session', { idea: 'valid idea', page: 51 })).rejects.toThrow('Invalid search request');
  await expect(searchProjects('session', { idea: 'valid idea', perPage: 101 })).rejects.toThrow('Invalid search request');
  expect(fetcher).not.toHaveBeenCalled();
});

test('bad search payloads are rejected by the response schema', async () => {
  jest.spyOn(global, 'fetch').mockResolvedValue(
    response(200, { ...results, items: [{ ...project, stars: 'many' }] }) as Response,
  );
  await expect(searchProjects('session', { idea: 'task manager' })).rejects.toBeInstanceOf(DiscoveryResponseError);
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

test('a 503 with Retry-After is reported as a rate limit, not a generic outage', async () => {
  jest.spyOn(global, 'fetch').mockResolvedValue(response(503, {}, { 'Retry-After': '45' }) as Response);
  const failure = await searchProjects('session', { idea: 'task manager' }).catch(error => error);
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

test('details and favourites share the transport, encode repository paths and handle 204 deletes', async () => {
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
])('backend status %s maps to a user-facing message', async (status, message) => {
  jest.spyOn(global, 'fetch').mockResolvedValue(response(status) as Response);
  await expect(getFavourites('session')).rejects.toThrow(message);
});

test('invalid repository paths are rejected before a request', () => {
  expect(() => getProject('session', 'owner')).toThrow('Invalid repository name');
  expect(() => saveFavourite('session', 'owner/name/extra')).toThrow('Invalid repository name');
});
