import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { AppProvider } from '../src/app/provider';
import { DiscoveryScreen } from '../src/features/discovery/components/discovery-screen';
import * as api from '../src/features/discovery/api/discovery';
import { loadCachedResults, saveCachedResults } from '../src/features/discovery/cache';

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
const second = {
  ...project,
  id: 2,
  name: 'navigator',
  full_name: 'octocat/navigator',
  description: 'Plan journeys',
};
const details = {
  ...project,
  languages: { Python: 90 },
  releases: [{ name: 'First release', tag: 'v1', published_at: null }],
  readme: '# Compass\nDiscover projects',
  readme_truncated: false,
  contributors: [{ login: 'maintainer', avatar_url: '', contributions: 8 }],
};
const results = (items: typeof project[], page = 1, incomplete = false, total = items.length) => ({
  items,
  total,
  incomplete,
  page,
  per_page: 20,
  sort: 'relevance',
  order: 'desc',
  source: 'github_keywords',
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
  jest.mocked(api.searchProjects).mockResolvedValue(results([project]));
  jest.mocked(api.getProject).mockResolvedValue(details);
  jest.mocked(api.saveFavourite).mockResolvedValue(project);
  jest.mocked(api.removeFavourite).mockResolvedValue(undefined);
});

test('search renders name, description, stars, language and an honest licence placeholder', async () => {
  const screen = await open();
  await waitFor(() => expect(api.getFavourites).toHaveBeenCalledWith('session'));
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(screen.getByText('Find similar projects')).toBeTruthy();
  expect(screen.getByText('42 stars')).toBeTruthy();
  expect(screen.getByText('Python')).toBeTruthy();
  expect(screen.getByText('Licence not reported')).toBeTruthy();
  expect(api.searchProjects).toHaveBeenCalledWith('session', { idea: 'task manager', page: 1 });
});

test('empty results are shown as no matches', async () => {
  jest.mocked(api.searchProjects).mockResolvedValue(results([]));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('No projects matched your idea. Try different keywords.')).toBeTruthy());
});

test('incomplete results say they may be partial and never claim no matches', async () => {
  jest.mocked(api.searchProjects).mockResolvedValue(results([], 1, true, 0));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('Results may be partial. GitHub returned an incomplete set.')).toBeTruthy());
  expect(screen.queryByText('No projects matched your idea. Try different keywords.')).toBeNull();
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

test('load more appends the next page', async () => {
  jest.mocked(api.searchProjects)
    .mockResolvedValueOnce(results([project], 1, false, 2))
    .mockResolvedValueOnce(results([second], 2, false, 2));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByText('Load more'));
  await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
  expect(screen.getByText('compass')).toBeTruthy();
  expect(api.searchProjects).toHaveBeenLastCalledWith('session', { idea: 'task manager', page: 2 });
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
  await saveCachedResults('123', results([project]));
  const screen = await open();
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(api.searchProjects).not.toHaveBeenCalled();
});

test('search results are cached per account without persisting the raw idea', async () => {
  const idea = 'secret quantum banana idea';
  const screen = await open();
  await search(screen, idea);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await waitFor(async () => expect((await loadCachedResults('123'))?.data.items[0].name).toBe('compass'));
  const keys = await AsyncStorage.getAllKeys();
  const entries = await AsyncStorage.multiGet(keys);
  for (const [, value] of entries) expect(value ?? '').not.toContain(idea);
});

test('switching accounts clears the previous account cache and state', async () => {
  await saveCachedResults('123', results([project]));
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
  await waitFor(async () => expect(await loadCachedResults('123')).toBeNull());
  await waitFor(() => expect(screen.queryByText('compass')).toBeNull());
});

test('signing out clears the account cache before leaving', async () => {
  const onSignOut = jest.fn();
  await saveCachedResults('123', results([project]));
  const screen = await open({ onSignOut });
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByText('Sign out'));
  await waitFor(() => expect(onSignOut).toHaveBeenCalled());
  await waitFor(async () => expect(await loadCachedResults('123')).toBeNull());
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
    .mockResolvedValueOnce(results([project], 1, false, 2))
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
  jest.mocked(api.searchProjects).mockResolvedValue(results([{ ...project, description: '', language: null }]));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(screen.getByText('Language not reported')).toBeTruthy();
  expect(screen.getByText('Licence not reported')).toBeTruthy();
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
  await saveCachedResults('123', results([project], 1, false, 5));
  const screen = await open();
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(screen.queryByText('Load more')).toBeNull();
  expect(screen.getByText('Showing your last results. Search again to load more.')).toBeTruthy();
  expect(api.searchProjects).not.toHaveBeenCalled();
});

test('a slow load-more response cannot overwrite a newer search', async () => {
  let resolveMore!: (value: ReturnType<typeof results>) => void;
  jest.mocked(api.searchProjects)
    .mockResolvedValueOnce(results([project], 1, false, 2))
    .mockReturnValueOnce(new Promise(resolve => { resolveMore = resolve; }))
    .mockResolvedValueOnce(results([second], 1, false, 1));
  const screen = await open();
  await search(screen, 'first idea');
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByText('Load more'));
  await waitFor(() => expect(screen.getByText('Loading more')).toBeTruthy());
  await fireEvent.changeText(screen.getByLabelText('Project idea'), 'second idea');
  await fireEvent.press(screen.getByText('Search projects'));
  await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
  await act(async () => { resolveMore(results([project, second], 2, false, 2)); });
  expect(screen.getByText('navigator')).toBeTruthy();
  expect(screen.queryByText('compass')).toBeNull();
});

test('details opened later win when an earlier response resolves last', async () => {
  jest.mocked(api.searchProjects).mockResolvedValue(results([project, second]));
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
    .mockResolvedValueOnce(results([project], 1, false, 3))
    .mockResolvedValueOnce(results([project, second], 2, false, 3));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByText('Load more'));
  await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
  expect(screen.getAllByText('compass')).toHaveLength(1);
  expect(consoleError.mock.calls.flat().join(' ')).not.toContain('same key');
  consoleError.mockRestore();
});
