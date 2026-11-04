import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { AppProvider } from '../src/app/provider';
import { DiscoveryScreen } from '../src/features/discovery/components/discovery-screen';
import * as api from '../src/features/discovery/api/discovery';
import * as cache from '../src/features/discovery/cache';

jest.mock('../src/features/discovery/api/discovery', () => ({
  ...jest.requireActual('../src/features/discovery/api/discovery'),
  searchProjects: jest.fn(),
  getProject: jest.fn(),
  getFavourites: jest.fn(),
  saveFavourite: jest.fn(),
  removeFavourite: jest.fn(),
}));

const project: api.Project = {
  id: 1,
  name: 'compass',
  full_name: 'octocat/compass',
  owner: 'octocat',
  avatar_url: '',
  description: 'Find similar projects',
  stars: 42,
  language: 'Python',
  url: 'https://github.com/octocat/compass',
};

const details = {
  ...project,
  languages: { Python: 90 },
  releases: [{ name: 'First release', tag: 'v1', published_at: null }],
  readme: '# Compass\nDiscover projects',
  readme_truncated: false,
  contributors: [{ login: 'maintainer', avatar_url: '', contributions: 8 }],
};
const sourceOk = { status: 'ok', incomplete: false, reason: null, retry_after: null };
const archiveOk = { ...sourceOk, coverage: 'unknown' };
const item = (overrides: Partial<api.SearchItem> = {}): api.SearchItem => ({
  ...project,
  sources: ['github'],
  license: null,
  license_conflict: false,
  matched_section: null,
  snippet: null,
  freshness: 'live',
  rank: 1,
  rrf_score: 0.01,
  ...overrides,
});
const searchSecond = item({
  id: 2,
  name: 'navigator',
  full_name: 'octocat/navigator',
  description: 'Plan journeys',
});
const results = (
  items: api.SearchItem[],
  next: string | null = null,
  overrides: Partial<api.SearchResults> = {},
): api.SearchResults => ({
  items,
  next_cursor: next,
  has_more: next !== null,
  total: null,
  degraded: false,
  sources: { github: sourceOk, archive: archiveOk },
  archive_as_of: null,
  ranking_version: 'rrf-v1',
  generation: `${'a'.repeat(40)}:rrf-v1`,
  ...overrides,
});
const user = { github_id: 123, login: 'octocat', avatar_url: '' };

const open = (overrides: Partial<React.ComponentProps<typeof DiscoveryScreen>> = {}) =>
  render(
    <AppProvider>
      <DiscoveryScreen
        token="session"
        user={user}
        onSignOut={jest.fn()}
        signingOut={false}
        accountError=""
        onUnauthorized={jest.fn()}
        {...overrides}
      />
    </AppProvider>,
  );

const search = async (screen: Awaited<ReturnType<typeof open>>, idea = 'task manager') => {
  await fireEvent.changeText(screen.getByLabelText('Project idea'), idea);
  await fireEvent.press(screen.getByText('Search projects'));
};

beforeEach(async () => {
  jest.clearAllMocks();
  await AsyncStorage.clear();
  jest.mocked(api.getFavourites).mockResolvedValue({ items: [] });
  jest.mocked(api.searchProjects).mockResolvedValue(results([item()]));
  jest.mocked(api.getProject).mockResolvedValue(details);
  jest.mocked(api.saveFavourite).mockResolvedValue(project);
  jest.mocked(api.removeFavourite).mockResolvedValue(undefined);
});

afterEach(() => jest.restoreAllMocks());

test('search renders name, description, stars, language and an honest licence placeholder', async () => {
  const screen = await open();
  await waitFor(() => expect(api.getFavourites).toHaveBeenCalledWith('session'));
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(screen.getByText('Find similar projects')).toBeTruthy();
  expect(screen.getByText('42 stars')).toBeTruthy();
  expect(screen.getByText('Python')).toBeTruthy();
  expect(screen.getByText('Licence not reported')).toBeTruthy();
  expect(screen.getByText('Source: Live')).toBeTruthy();
  expect(api.searchProjects).toHaveBeenCalledWith('session', { idea: 'task manager', pageSize: 20 });
});

test('the loading label says "Searching projects", not a source name', async () => {
  let resolveSearch!: (value: api.SearchResults) => void;
  jest.mocked(api.searchProjects).mockReturnValue(new Promise(resolve => { resolveSearch = resolve; }));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByLabelText('Searching projects')).toBeTruthy());
  expect(screen.queryByText('Searching GitHub')).toBeNull();
  await act(async () => { resolveSearch(results([item()])); });
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
});

test('empty results are shown as no matches', async () => {
  jest.mocked(api.searchProjects).mockResolvedValue(results([]));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('No projects matched your idea. Try different keywords.')).toBeTruthy());
});

test.each([
  ['SEARCH_INCOMPLETE', 503, 'Results may be partial. Try again in a moment.'],
  ['SEARCH_BUSY', 503, 'Search is busy. Try again shortly.'],
  ['SEARCH_TIMEOUT', 503, 'Search timed out. Try again.'],
  ['SEARCH_UNAVAILABLE', 503, 'Search is starting or unavailable. Try again shortly.'],
])('%s shows its own state and never claims no matches', async (code, status, message) => {
  jest.mocked(api.searchProjects).mockRejectedValue(new api.DiscoveryApiError(message, status, code, true));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText(message)).toBeTruthy());
  expect(screen.queryByText('No projects matched your idea. Try different keywords.')).toBeNull();
});

test('a degraded search says results may be incomplete', async () => {
  jest.mocked(api.searchProjects).mockResolvedValue(results([item()], null, {
    degraded: true,
    sources: { github: { status: 'failed', incomplete: true, reason: 'timeout', retry_after: null }, archive: archiveOk },
  }));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('Some sources were unavailable. Results may be incomplete.')).toBeTruthy());
  expect(screen.getByText('compass')).toBeTruthy();
});

test('rate limiting shows the Retry-After message', async () => {
  jest.mocked(api.searchProjects).mockRejectedValue(new api.DiscoveryApiError('Too many requests. Try again in 30 seconds.', 429));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('Too many requests. Try again in 30 seconds.')).toBeTruthy());
});

test('an unauthorised search returns the user to sign-in', async () => {
  const onUnauthorized = jest.fn();
  jest.mocked(api.searchProjects).mockRejectedValue(new api.DiscoveryApiError('Your session expired. Sign in again.', 401));
  const screen = await open({ onUnauthorized });
  await search(screen);
  await waitFor(() => expect(onUnauthorized).toHaveBeenCalled());
});

test('network failures show a retryable connection message', async () => {
  jest.mocked(api.searchProjects).mockRejectedValue(new api.DiscoveryNetworkError('Unable to connect. Check your connection and try again.'));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('Unable to connect. Check your connection and try again.')).toBeTruthy());
});

test('load more sends the cursor and appends the next page', async () => {
  jest.mocked(api.searchProjects)
    .mockResolvedValueOnce(results([item()], 'cursor-2'))
    .mockResolvedValueOnce(results([searchSecond], null));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByText('Load more'));
  await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
  expect(screen.getByText('compass')).toBeTruthy();
  expect(api.searchProjects).toHaveBeenLastCalledWith('session', { idea: 'task manager', pageSize: 20, cursor: 'cursor-2' });
});

test('load more disappears when has_more is false', async () => {
  jest.mocked(api.searchProjects)
    .mockResolvedValueOnce(results([item()], 'cursor-2'))
    .mockResolvedValueOnce(results([searchSecond], null));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByText('Load more'));
  await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
  expect(screen.queryByText('Load more')).toBeNull();
});

test('an expired cursor clears the cursor, keeps the idea and asks for a fresh search', async () => {
  jest.mocked(api.searchProjects)
    .mockResolvedValueOnce(results([item()], 'stale-cursor'))
    .mockRejectedValueOnce(new api.DiscoveryApiError('This search expired. Start a new search.', 410, 'CURSOR_EXPIRED'))
    .mockResolvedValueOnce(results([searchSecond], null));
  const screen = await open();
  await search(screen, 'first idea');
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByText('Load more'));
  await waitFor(() => expect(screen.getByText('This search expired. Search again to see more results.')).toBeTruthy());
  expect(screen.queryByText('Load more')).toBeNull();
  expect(screen.getByLabelText('Project idea').props.value).toBe('first idea');
  await fireEvent.press(screen.getByText('Search projects'));
  await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
  expect(api.searchProjects).toHaveBeenLastCalledWith('session', { idea: 'first idea', pageSize: 20 });
});

test('details open from a result and the favourite toggle saves optimistically', async () => {
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByLabelText('Open octocat/compass'));
  await waitFor(() => expect(screen.getByText('# Compass\nDiscover projects')).toBeTruthy());
  expect(screen.getByText('Contributors')).toBeTruthy();
  expect(screen.getByText('maintainer')).toBeTruthy();
  await fireEvent.press(screen.getByLabelText('Save octocat/compass to favourites'));
  await waitFor(() => expect(api.saveFavourite).toHaveBeenCalledWith('session', 'octocat/compass'));
  await waitFor(() => expect(screen.getByLabelText('Remove octocat/compass from favourites')).toBeTruthy());
});

test('a failed save rolls the optimistic favourite back', async () => {
  let rejectSave!: (error: Error) => void;
  jest.mocked(api.saveFavourite).mockReturnValue(new Promise((_, reject) => { rejectSave = reject; }));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByLabelText('Save octocat/compass to favourites'));
  await waitFor(() => expect(screen.getByLabelText('Remove octocat/compass from favourites')).toBeTruthy());
  rejectSave(new Error('offline'));
  await waitFor(() => expect(screen.getByText('Unable to update favourites. Please try again.')).toBeTruthy());
  expect(screen.getByLabelText('Save octocat/compass to favourites')).toBeTruthy();
});

test('a failed remove restores the favourite in the list', async () => {
  jest.mocked(api.getFavourites).mockResolvedValue({ items: [project] });
  let rejectRemove!: (error: Error) => void;
  jest.mocked(api.removeFavourite).mockReturnValue(new Promise((_, reject) => { rejectRemove = reject; }));
  const screen = await open();
  await waitFor(() => expect(api.getFavourites).toHaveBeenCalled());
  await fireEvent.press(screen.getByRole('tab', { name: 'Favourites' }));
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByLabelText('Remove octocat/compass from favourites'));
  await waitFor(() => expect(screen.queryByText('compass')).toBeNull());
  rejectRemove(new Error('offline'));
  await waitFor(() => expect(screen.getByText('Unable to update favourites. Please try again.')).toBeTruthy());
  expect(screen.getByText('compass')).toBeTruthy();
  expect(screen.getByLabelText('Remove octocat/compass from favourites')).toBeTruthy();
});

test('the last cached results load before a new search', async () => {
  await cache.saveCachedResults('123', results([item()]));
  const screen = await open();
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(api.searchProjects).not.toHaveBeenCalled();
});

test('search results are cached per account without persisting the raw idea or cursor', async () => {
  const idea = 'secret quantum banana idea';
  jest.mocked(api.searchProjects).mockResolvedValue(results([item()], 'secret-cursor'));
  const screen = await open();
  await search(screen, idea);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await waitFor(async () => expect((await cache.loadCachedResults('123'))?.data.items[0].name).toBe('compass'));
  const keys = await AsyncStorage.getAllKeys();
  const entries = await AsyncStorage.multiGet(keys);
  for (const [, value] of entries) {
    expect(value ?? '').not.toContain(idea);
    expect(value ?? '').not.toContain('secret-cursor');
  }
  expect((await cache.loadCachedResults('123'))?.data.next_cursor).toBeNull();
});

test('switching accounts clears the previous account cache and state', async () => {
  await cache.saveCachedResults('123', results([item()]));
  const screen = await open();
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  screen.rerender(
    <AppProvider>
      <DiscoveryScreen
        token="session"
        user={{ ...user, github_id: 456 }}
        onSignOut={jest.fn()}
        signingOut={false}
        accountError=""
        onUnauthorized={jest.fn()}
      />
    </AppProvider>,
  );
  await waitFor(async () => expect(await cache.loadCachedResults('123')).toBeNull());
  await waitFor(() => expect(screen.queryByText('compass')).toBeNull());
});

test('signing out clears the account cache before leaving', async () => {
  const onSignOut = jest.fn();
  await cache.saveCachedResults('123', results([item()]));
  const screen = await open({ onSignOut });
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByText('Sign out'));
  await waitFor(() => expect(onSignOut).toHaveBeenCalled());
  await waitFor(async () => expect(await cache.loadCachedResults('123')).toBeNull());
});

test('a too-short idea is rejected before any request', async () => {
  const screen = await open();
  await fireEvent.changeText(screen.getByLabelText('Project idea'), 'a');
  await fireEvent.press(screen.getByText('Search projects'));
  await waitFor(() => expect(screen.getByText('Describe your idea')).toBeTruthy());
  expect(api.searchProjects).not.toHaveBeenCalled();
});

test('unknown search failures use the generic fallback', async () => {
  jest.mocked(api.searchProjects).mockRejectedValue(new Error('boom'));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('Search failed. Please try again.')).toBeTruthy());
});

test('a failed favourites refresh keeps discovery usable and offers a message', async () => {
  jest.mocked(api.getFavourites).mockRejectedValue(new Error('offline'));
  const screen = await open();
  await waitFor(() => expect(screen.getByText('Unable to refresh favourites. Please try again.')).toBeTruthy());
  expect(screen.getByLabelText('Project idea')).toBeTruthy();
});

test('an unauthorised favourites refresh returns the user to sign-in', async () => {
  const onUnauthorized = jest.fn();
  jest.mocked(api.getFavourites).mockRejectedValue(new api.DiscoveryApiError('expired', 401));
  await open({ onUnauthorized });
  await waitFor(() => expect(onUnauthorized).toHaveBeenCalled());
});

test('load more failures keep the first page and show a retry message', async () => {
  jest.mocked(api.searchProjects)
    .mockResolvedValueOnce(results([item()], 'cursor-2'))
    .mockRejectedValueOnce(new Error('offline'));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByText('Load more'));
  await waitFor(() => expect(screen.getByText('Unable to load more results. Please try again.')).toBeTruthy());
  expect(screen.getByText('compass')).toBeTruthy();
});

test('an unauthorised favourite mutation returns the user to sign-in', async () => {
  const onUnauthorized = jest.fn();
  jest.mocked(api.saveFavourite).mockRejectedValue(new api.DiscoveryApiError('expired', 401));
  const screen = await open({ onUnauthorized });
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByLabelText('Save octocat/compass to favourites'));
  await waitFor(() => expect(onUnauthorized).toHaveBeenCalled());
});

test('detail failures can be retried by going back', async () => {
  jest.mocked(api.getProject).mockRejectedValue(new Error('offline'));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByLabelText('Open octocat/compass'));
  await waitFor(() => expect(screen.getByText('Unable to load this project. Please try again.')).toBeTruthy());
  await fireEvent.press(screen.getByLabelText('Go back'));
  expect(screen.getByLabelText('Project idea')).toBeTruthy();
});

test('details show a provided licence and omit empty sections', async () => {
  jest.mocked(api.getProject).mockResolvedValue({
    ...project,
    license: 'MIT',
    languages: {},
    releases: [],
    readme: 'Read me',
    readme_truncated: true,
    contributors: [],
  });
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByLabelText('Open octocat/compass'));
  await waitFor(() => expect(screen.getByText('Licence MIT')).toBeTruthy());
  expect(screen.getByText('README truncated.')).toBeTruthy();
  expect(screen.queryByText('Languages')).toBeNull();
  expect(screen.queryByText('Releases')).toBeNull();
  expect(screen.queryByText('Contributors')).toBeNull();
});

test('cards show honest fallbacks for missing language and licence', async () => {
  jest.mocked(api.searchProjects).mockResolvedValue(results([item({ description: '', language: null })]));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(screen.getByText('Language not reported')).toBeTruthy();
  expect(screen.getByText('Licence not reported')).toBeTruthy();
});

test('a licence conflict shows the live licence and hides the archive snippet', async () => {
  jest.mocked(api.searchProjects).mockResolvedValue(results([item({
    license: 'MIT',
    license_conflict: true,
    sources: ['github', 'archive'],
    freshness: 'live+archive',
    snippet: 'Archive excerpt that must not be shown',
  })]));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(screen.getByText('Licence MIT')).toBeTruthy();
  expect(screen.queryByText('Archive excerpt that must not be shown')).toBeNull();
});

test('archive cards show their excerpt, licence and source label', async () => {
  jest.mocked(api.searchProjects).mockResolvedValue(results([item({
    sources: ['archive'],
    freshness: 'archive',
    license: 'Apache-2.0',
    snippet: 'Feature excerpt from the archive',
    matched_section: 'Features',
  })]));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(screen.getByText('Feature excerpt from the archive')).toBeTruthy();
  expect(screen.getByText('Licence Apache-2.0')).toBeTruthy();
  expect(screen.getByText('Source: Archive')).toBeTruthy();
});

test('signing-out and account errors are visible', async () => {
  const screen = await open({ signingOut: true, accountError: 'Your session expired.' });
  expect(screen.getByText('Signing out')).toBeTruthy();
  expect(screen.getByText('Your session expired.')).toBeTruthy();
});

test('favourites open the same details view', async () => {
  jest.mocked(api.getFavourites).mockResolvedValue({ items: [project] });
  const screen = await open();
  await waitFor(() => expect(api.getFavourites).toHaveBeenCalled());
  await fireEvent.press(screen.getByRole('tab', { name: 'Favourites' }));
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByLabelText('Open octocat/compass'));
  await waitFor(() => expect(api.getProject).toHaveBeenCalledWith('session', 'octocat/compass'));
});

test('the favourites tab starts with an empty state', async () => {
  const screen = await open();
  await fireEvent.press(screen.getByRole('tab', { name: 'Favourites' }));
  expect(screen.getByText('No favourites yet.')).toBeTruthy();
});

test('a cached page without an idea offers no load more and explains why', async () => {
  await cache.saveCachedResults('123', results([item()], 'stored-cursor'));
  const screen = await open();
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(screen.queryByText('Load more')).toBeNull();
  expect(screen.getByText('Showing your last results. Search again to load more.')).toBeTruthy();
  expect(api.searchProjects).not.toHaveBeenCalled();
});

test('a search started before the cache restore wins over the cached page', async () => {
  let resolveCache!: (value: { data: api.SearchResults; savedAt: number }) => void;
  jest.spyOn(cache, 'loadCachedResults').mockReturnValueOnce(new Promise(resolve => { resolveCache = resolve; }));
  jest.mocked(api.searchProjects).mockResolvedValue(results([searchSecond]));
  const screen = await open();
  await search(screen, 'fresh idea');
  await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
  await act(async () => { resolveCache({ data: results([item()]), savedAt: Date.now() }); });
  expect(screen.getByText('navigator')).toBeTruthy();
  expect(screen.queryByText('compass')).toBeNull();
});

test('a slow load-more response cannot overwrite a newer search', async () => {
  let resolveMore!: (value: ReturnType<typeof results>) => void;
  jest.mocked(api.searchProjects)
    .mockResolvedValueOnce(results([item()], 'cursor-2'))
    .mockReturnValueOnce(new Promise(resolve => { resolveMore = resolve; }))
    .mockResolvedValueOnce(results([searchSecond], null));
  const screen = await open();
  await search(screen, 'first idea');
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByText('Load more'));
  await waitFor(() => expect(screen.getByText('Loading more')).toBeTruthy());
  await fireEvent.changeText(screen.getByLabelText('Project idea'), 'second idea');
  await fireEvent.press(screen.getByText('Search projects'));
  await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
  await act(async () => { resolveMore(results([item(), searchSecond], null)); });
  expect(screen.getByText('navigator')).toBeTruthy();
  expect(screen.queryByText('compass')).toBeNull();
});

test('details opened later win when an earlier response resolves last', async () => {
  jest.mocked(api.searchProjects).mockResolvedValue(results([item(), searchSecond]));
  let resolveA!: (value: typeof details) => void;
  jest.mocked(api.getProject)
    .mockReturnValueOnce(new Promise(resolve => { resolveA = resolve; }))
    .mockResolvedValueOnce({ ...details, name: 'navigator', full_name: 'octocat/navigator', readme: 'Navigator readme' });
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
  await fireEvent.press(screen.getByLabelText('Open octocat/compass'));
  await fireEvent.press(screen.getByLabelText('Go back'));
  await fireEvent.press(screen.getByLabelText('Open octocat/navigator'));
  await waitFor(() => expect(screen.getByText('Navigator readme')).toBeTruthy());
  await act(async () => { resolveA({ ...details, readme: 'Compass readme' }); });
  expect(screen.getByText('Navigator readme')).toBeTruthy();
  expect(screen.queryByText('Compass readme')).toBeNull();
});

test('a repeated project across pages is shown once', async () => {
  const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);
  jest.mocked(api.searchProjects)
    .mockResolvedValueOnce(results([item()], 'cursor-2'))
    .mockResolvedValueOnce(results([item(), searchSecond], null));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByText('Load more'));
  await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
  expect(screen.getAllByText('compass')).toHaveLength(1);
  expect(consoleError.mock.calls.flat().join(' ')).not.toContain('same key');
  consoleError.mockRestore();
});

// T25: one combined list with truthful states.
const githubFailed = { status: 'failed', incomplete: true, reason: 'timeout', retry_after: null };
const archiveFailed = { status: 'failed', incomplete: true, reason: 'unavailable', retry_after: null, coverage: 'unknown' };

test('GitHub-only, archive-only and common cards render in one list without a source selector', async () => {
  jest.mocked(api.searchProjects).mockResolvedValue(results([
    item({ id: 1, full_name: 'octocat/live', name: 'live', freshness: 'live', sources: ['github'] }),
    item({ id: 2, full_name: 'octocat/stored', name: 'stored', freshness: 'archive', sources: ['archive'], snippet: 'Stored README excerpt' }),
    item({ id: 3, full_name: 'octocat/both', name: 'both', freshness: 'live+archive', sources: ['github', 'archive'] }),
  ]));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('both')).toBeTruthy());
  expect(screen.getByText('live')).toBeTruthy();
  expect(screen.getByText('stored')).toBeTruthy();
  expect(screen.getByText('Source: Live')).toBeTruthy();
  expect(screen.getByText('Source: Archive')).toBeTruthy();
  expect(screen.getByText('Source: Live + archive')).toBeTruthy();
  expect(screen.queryByText(/%/)).toBeNull();
  expect(screen.queryByRole('tab', { name: /archive|github/i })).toBeNull();
});

test('a partial search with results names the missing source', async () => {
  jest.mocked(api.searchProjects).mockResolvedValue(results([item()], null, {
    degraded: true,
    sources: { github: sourceOk, archive: archiveFailed },
  }));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('Some sources were unavailable. Results may be incomplete.')).toBeTruthy());
  expect(screen.getByText('The project archive did not respond, so only live GitHub results are shown.')).toBeTruthy();
  expect(screen.queryByText('No projects matched your idea. Try different keywords.')).toBeNull();
});

test('a partial search with zero results never claims no matches and offers a retry', async () => {
  jest.mocked(api.searchProjects)
    .mockResolvedValueOnce(results([], null, { degraded: true, sources: { github: githubFailed, archive: archiveOk } }))
    .mockResolvedValueOnce(results([item()]));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('No results could be confirmed because a source was unavailable.')).toBeTruthy());
  expect(screen.getByText('Live GitHub search did not respond, so only archive results are shown.')).toBeTruthy();
  expect(screen.queryByText('No projects matched your idea. Try different keywords.')).toBeNull();
  await fireEvent.press(screen.getByRole('button', { name: 'Try again' }));
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(jest.mocked(api.searchProjects).mock.calls[1][1]).toEqual({ idea: 'task manager', pageSize: 20 });
});

test('only a complete healthy empty search says no matches', async () => {
  jest.mocked(api.searchProjects).mockResolvedValue(results([], null, {
    sources: { github: sourceOk, archive: { ...archiveOk, status: 'incomplete', incomplete: true } },
  }));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('No results could be confirmed because a source was unavailable.')).toBeTruthy());
  expect(screen.queryByText('No projects matched your idea. Try different keywords.')).toBeNull();
});

test('a failed search offers a retry with the same idea', async () => {
  jest.mocked(api.searchProjects)
    .mockRejectedValueOnce(new api.DiscoveryApiError('Search is busy. Try again shortly.', 503, 'SEARCH_BUSY', true))
    .mockResolvedValueOnce(results([item()]));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('Search is busy. Try again shortly.')).toBeTruthy());
  await fireEvent.changeText(screen.getByLabelText('Project idea'), 'edited but not submitted');
  await fireEvent.press(screen.getByRole('button', { name: 'Try again' }));
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(jest.mocked(api.searchProjects).mock.calls[1][1]).toEqual({ idea: 'task manager', pageSize: 20 });
});

test('cached results always carry a stale banner, even without more pages', async () => {
  await cache.saveCachedResults('123', results([item()]));
  const screen = await open();
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(screen.getByText('Showing your last results. Search again for fresh results.')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull();
});

test('pull to refresh starts a new hybrid search for the current idea', async () => {
  jest.mocked(api.searchProjects)
    .mockResolvedValueOnce(results([item()], 'first-cursor'))
    .mockResolvedValueOnce(results([searchSecond]));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  const list = screen.getByTestId('discovery-list');
  await act(async () => { await list.props.refreshControl.props.onRefresh(); });
  await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
  expect(screen.queryByText('compass')).toBeNull();
  expect(jest.mocked(api.searchProjects).mock.calls[1][1]).toEqual({ idea: 'task manager', pageSize: 20 });
});

test('pull to refresh is not offered without a live idea or outside Home results', async () => {
  await cache.saveCachedResults('123', results([item()]));
  const screen = await open();
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(screen.getByTestId('discovery-list').props.refreshControl).toBeUndefined();
  await fireEvent.press(screen.getByRole('tab', { name: 'Favourites' }));
  expect(screen.getByTestId('discovery-list').props.refreshControl).toBeUndefined();
});

test('a search that resolves after sign-out is not written back to the cache', async () => {
  let resolve: (value: api.SearchResults) => void = () => undefined;
  jest.mocked(api.searchProjects).mockImplementation(() => new Promise(done => { resolve = done; }));
  const onSignOut = jest.fn();
  const screen = await open({ onSignOut });
  await search(screen);
  await fireEvent.press(screen.getByText('Sign out'));
  await waitFor(() => expect(onSignOut).toHaveBeenCalled());
  await act(async () => { resolve(results([item()])); });
  expect(await cache.loadCachedResults('123')).toBeNull();
});

test('a favourite saved after sign-out is not written back to the cache', async () => {
  let resolve: (value: api.Project) => void = () => undefined;
  jest.mocked(api.saveFavourite).mockImplementation(() => new Promise(done => { resolve = done; }));
  const onSignOut = jest.fn();
  const screen = await open({ onSignOut });
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByLabelText('Save octocat/compass to favourites'));
  await fireEvent.press(screen.getByText('Sign out'));
  await waitFor(() => expect(onSignOut).toHaveBeenCalled());
  await act(async () => { resolve(project); });
  expect(await cache.loadCachedFavourites('123')).toBeNull();
});

test('a search that resolves after unmount is not written to the cache', async () => {
  let resolve: (value: api.SearchResults) => void = () => undefined;
  jest.mocked(api.searchProjects).mockImplementation(() => new Promise(done => { resolve = done; }));
  const screen = await open();
  await search(screen);
  await act(async () => { screen.unmount(); });
  await act(async () => { resolve(results([item()])); });
  expect(await cache.loadCachedResults('123')).toBeNull();
});
