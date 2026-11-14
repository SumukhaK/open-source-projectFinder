import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { AppProvider } from '../src/app/provider';
import { DiscoveryScreen } from '../src/features/discovery/components/discovery-screen';
import * as api from '../src/features/discovery/api/discovery';
import * as cache from '../src/features/discovery/cache';
import { AudioModule, createAudioPlayer, setAudioModeAsync } from 'expo-audio';
import { AccessibilityInfo, AppState, AppStateStatus, Linking } from 'react-native';
import { fetch as summaryFetch } from 'expo/fetch';
import { summaryStream } from './summary-stream';
import { uploadRecording } from '../src/features/discovery/voice-api';

jest.mock('../src/features/discovery/voice-api', () => ({ ...jest.requireActual('../src/features/discovery/voice-api'), uploadRecording: jest.fn() }));

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

test('voice asks for consent while text search stays available', async () => {
  const screen = await open();
  expect(screen.getByText('Hold the mic to say your idea.')).toBeTruthy();
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressIn');
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressOut');
  expect(screen.getByText('Search by voice')).toBeTruthy();
  await fireEvent.press(screen.getByText('Not now'));
  expect(screen.queryByText('Search by voice')).toBeNull();
  await search(screen);
  await waitFor(() => expect(api.searchProjects).toHaveBeenCalled());
});

test('Profile links to microphone status and voice explanation', async () => {
  const screen = await open();
  await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
  await fireEvent.press(screen.getByRole('button', { name: 'Voice' }));
  expect(screen.getByText(/Microphone:/)).toBeTruthy();
  await fireEvent.press(screen.getByText('How voice works'));
  expect(screen.getByText(/Deepgram/)).toBeTruthy();
  await fireEvent.press(screen.getByText('Back to Voice'));
  await fireEvent.press(screen.getByText('Back to Profile'));
  expect(screen.getByText('Settings')).toBeTruthy();
});

test('voice transcript is visible and editable before the existing search receives it', async () => {
  await AsyncStorage.setItem('reporadar.voice.123.consent', 'yes');
  jest.mocked(uploadRecording).mockResolvedValue('voice maps');
  const screen = await open();
  await waitFor(() => expect(screen.queryByText('Hold the mic to say your idea.')).toBeNull());
  jest.mocked(api.searchProjects).mockImplementation(async () => {
    expect(screen.getByText('We heard')).toBeTruthy();
    expect(screen.getByLabelText('Project idea').props.value).toBe('voice maps');
    return results([]);
  });
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressIn');
  await waitFor(() => expect(screen.getByText(/Let go to search/)).toBeTruthy());
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressOut');
  await waitFor(() => expect(api.searchProjects).toHaveBeenCalledWith('session', { idea: 'voice maps', pageSize: 20 }));
  jest.mocked(api.searchProjects).mockResolvedValue(results([]));
  await search(screen, 'edited maps');
  expect(api.searchProjects).toHaveBeenLastCalledWith('session', { idea: 'edited maps', pageSize: 20 });
});

test.each(['typing', 'submit', 'tab change'])('%s after voice search hides We heard', async action => {
  await AsyncStorage.setItem('reporadar.voice.123.consent', 'yes');
  jest.mocked(uploadRecording).mockResolvedValue('voice maps');
  const screen = await open();
  await waitFor(() => expect(screen.queryByText('Hold the mic to say your idea.')).toBeNull());
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressIn');
  await waitFor(() => expect(screen.getByText(/Let go to search/)).toBeTruthy());
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressOut');
  await waitFor(() => expect(api.searchProjects).toHaveBeenCalled());
  expect(screen.getByText('We heard')).toBeTruthy();
  if (action === 'typing') await fireEvent.changeText(screen.getByLabelText('Project idea'), 'typed maps');
  else if (action === 'submit') await fireEvent.press(screen.getByRole('button', { name: 'Search projects' }));
  else {
    await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
    await fireEvent.press(screen.getByRole('tab', { name: 'Home' }));
  }
  expect(screen.queryByText('We heard')).toBeNull();
});

test('consent Continue requests permission and denied sheet opens phone settings', async () => {
  jest.mocked(AudioModule.requestRecordingPermissionsAsync).mockResolvedValueOnce({ granted: false } as never);
  const settings = jest.spyOn(Linking, 'openSettings').mockResolvedValue(undefined);
  const screen = await open();
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressIn');
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressOut');
  await fireEvent.press(screen.getByText('Continue'));
  await waitFor(() => expect(screen.getByText('Microphone is off for RepoRadar')).toBeTruthy());
  await fireEvent.press(screen.getByText('Open phone settings'));
  expect(settings).toHaveBeenCalled();
  await fireEvent.press(screen.getByText('Not now'));
  expect(screen.getByLabelText('Project idea')).toBeTruthy();
});

test('sliding away cancels without uploading', async () => {
  await AsyncStorage.setItem('reporadar.voice.123.consent', 'yes');
  const screen = await open();
  await waitFor(() => expect(screen.queryByText('Hold the mic to say your idea.')).toBeNull());
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressIn', { nativeEvent: { pageX: 100, pageY: 100 } });
  await waitFor(() => expect(screen.getByText(/Let go to search/)).toBeTruthy());
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'touchMove', { nativeEvent: { pageX: 0, pageY: 100 } });
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressOut');
  expect(uploadRecording).not.toHaveBeenCalled();
});

test('header follows Home and Profile selection', async () => {
  const screen = await open();
  expect(screen.getByRole('header', { name: 'Discover projects' })).toBeTruthy();
  await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
  expect(screen.getByRole('header', { name: 'Profile' })).toBeTruthy();
  expect(screen.queryByRole('header', { name: 'Discover projects' })).toBeNull();
  await fireEvent.press(screen.getByRole('tab', { name: 'Home' }));
  expect(screen.getByRole('header', { name: 'Discover projects' })).toBeTruthy();
  expect(screen.queryByRole('header', { name: 'Profile' })).toBeNull();
});

test('Profile shows the username exactly once', async () => {
  const screen = await open();
  await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
  expect(screen.getAllByText('@octocat')).toHaveLength(1);
});

test('Home and Profile expose selected tabs and settings without a second search action', async () => {
  const screen = await open();
  expect(screen.getByRole('tab', { name: 'Home' }).props.accessibilityState.selected).toBe(true);
  expect(screen.queryByText('Sign out')).toBeNull();
  await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
  expect(screen.getByRole('tab', { name: 'Profile' }).props.accessibilityState.selected).toBe(true);
  expect(screen.getByText('Settings')).toBeTruthy();
  expect(screen.getByText('About and privacy')).toBeTruthy();
  expect(screen.getByLabelText('Dark appearance')).toBeTruthy();
  expect(screen.getByText('Sign out')).toBeTruthy();
  expect(screen.queryByLabelText('Project idea')).toBeNull();
  await fireEvent.press(screen.getByRole('tab', { name: 'Home' }));
  expect(screen.getByLabelText('Project idea')).toBeTruthy();
});

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
  AppState.currentState = 'active';
  jest.clearAllMocks();
  jest.mocked(api.searchProjects).mockReset();
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
  jest.mocked(api.searchProjects).mockRejectedValue(new api.DiscoveryApiError(message, status, code, false));
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
  await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
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
  await screen.rerender(
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
  await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
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
  expect(screen.queryByText('README excerpt')).toBeNull();
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
  // U5: the archive text is a partial README passage and is labelled as one.
  expect(screen.getByText('README excerpt')).toBeTruthy();
  expect(screen.getByLabelText('README excerpt: Feature excerpt from the archive')).toBeTruthy();
  expect(screen.getByText('Licence Apache-2.0')).toBeTruthy();
  expect(screen.getByText('Source: Archive')).toBeTruthy();
});

test('signing-out and account errors are visible', async () => {
  const screen = await open({ signingOut: true, accountError: 'Your session expired.' });
  await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
  expect(screen.getByText('Signing out')).toBeTruthy();
  expect(screen.getByText('Your session expired.')).toBeTruthy();
});

test('favourites open the same details view', async () => {
  jest.mocked(api.getFavourites).mockResolvedValue({ items: [project] });
  const screen = await open();
  await waitFor(() => expect(api.getFavourites).toHaveBeenCalled());
  await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await fireEvent.press(screen.getByLabelText('Open octocat/compass'));
  await waitFor(() => expect(api.getProject).toHaveBeenCalledWith('session', 'octocat/compass'));
});

test('the favourites tab starts with an empty state', async () => {
  const screen = await open();
  await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
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

test('pull to refresh keeps the current list and shows only the refresh spinner', async () => {
  let resolve: (value: api.SearchResults) => void = () => undefined;
  jest.mocked(api.searchProjects)
    .mockResolvedValueOnce(results([item()]))
    .mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  const screen = await open();
  await search(screen);
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  await act(async () => { void screen.getByTestId('discovery-list').props.refreshControl.props.onRefresh(); });
  expect(screen.getByTestId('discovery-list').props.refreshControl.props.refreshing).toBe(true);
  expect(screen.getByText('compass')).toBeTruthy();
  expect(screen.queryByLabelText('Searching projects')).toBeNull();
  await act(async () => { resolve(results([searchSecond])); });
  await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
  expect(screen.getByTestId('discovery-list').props.refreshControl.props.refreshing).toBe(false);
});

test('pull to refresh is not offered without a live idea or outside Home results', async () => {
  await cache.saveCachedResults('123', results([item()]));
  const screen = await open();
  await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
  expect(screen.getByTestId('discovery-list').props.refreshControl).toBeUndefined();
  await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
  expect(screen.getByTestId('discovery-list').props.refreshControl).toBeUndefined();
});

test('a search that resolves after sign-out is not written back to the cache', async () => {
  let resolve: (value: api.SearchResults) => void = () => undefined;
  jest.mocked(api.searchProjects).mockImplementation(() => new Promise(done => { resolve = done; }));
  const onSignOut = jest.fn();
  const screen = await open({ onSignOut });
  await search(screen);
  await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
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
  await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
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


describe('first-page summary', () => {
  test('list renders first, sends only ten full_names and announces only completion', async () => {
    const stream = summaryStream();
    const announce = jest.spyOn(AccessibilityInfo, 'announceForAccessibilityWithOptions').mockImplementation(() => {});
    const projects = Array.from({ length: 12 }, (_, i) => item({ id: i + 1, name: `repo${i}`, full_name: `owner/repo${i}` }));
    jest.mocked(api.searchProjects).mockResolvedValue(results(projects));
    const screen = await open();
    jest.mocked(summaryFetch).mockImplementationOnce(async () => {
      expect(screen.getByText('repo0')).toBeTruthy();
      return stream.response as never;
    });
    await search(screen);
    await waitFor(() => expect(summaryFetch).toHaveBeenCalled());
    expect(JSON.parse(jest.mocked(summaryFetch).mock.calls[0][1]!.body as string)).toEqual({ full_names: projects.slice(0, 10).map(p => p.full_name) });
    expect(screen.queryByText('Based only on the results below')).toBeNull();
    await act(async () => { stream.event('summary', { text: 'Useful projects' }); });
    expect(screen.getByText('Useful projects')).toBeTruthy();
    expect(screen.getByText('AI')).toBeTruthy();
    expect(announce).not.toHaveBeenCalled();
    await act(async () => { stream.event('done', { grounded: true, results: 10 }); });
    expect(announce).toHaveBeenCalledTimes(1);
    expect(announce).toHaveBeenCalledWith(expect.stringContaining('Useful projects'), { queue: true });
  });

  test.each(['ungrounded', 'network'])('%s hides the card without changing results', async failure => {
    const stream = summaryStream();
    jest.mocked(summaryFetch).mockResolvedValueOnce(stream.response as never);
    const screen = await open(); await search(screen);
    await waitFor(() => expect(summaryFetch).toHaveBeenCalled());
    await act(async () => { stream.event('summary', { text: 'Partial summary' }); });
    expect(screen.getByText('Partial summary')).toBeTruthy();
    await act(async () => { if (failure === 'network') stream.fail(); else stream.event('done', { grounded: false, reason: 'ungrounded' }); });
    expect(screen.queryByText('Partial summary')).toBeNull();
    expect(screen.getByText('compass')).toBeTruthy();
  });

  test.each(['new search', 'tab', 'sign-out', 'background', 'unmount'])('%s aborts and ignores late summary', async action => {
    let changed: (state: AppStateStatus) => void = () => {};
    jest.spyOn(AppState, 'addEventListener').mockImplementation((_, listener) => { const previous = changed; changed = state => { previous(state); listener(state); }; return { remove: jest.fn() }; });
    const stream = summaryStream();
    jest.mocked(summaryFetch).mockResolvedValueOnce(stream.response as never);
    const screen = await open(); await search(screen);
    await waitFor(() => expect(summaryFetch).toHaveBeenCalled());
    const signal = jest.mocked(summaryFetch).mock.calls[0][1]!.signal!;
    await act(async () => { stream.event('summary', { text: 'Old summary' }); });
    if (action === 'new search') await search(screen, 'new idea');
    else if (action === 'tab' || action === 'sign-out') {
      await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
      if (action === 'sign-out') await fireEvent.press(screen.getByText('Sign out'));
      else await fireEvent.press(screen.getByRole('tab', { name: 'Home' }));
    } else if (action === 'background') await act(async () => { changed('background'); });
    else await screen.unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => { stream.event('summary', { text: 'late' }); });
    if (action !== 'unmount') expect(screen.queryByText(/Old summary/)).toBeNull();
  });

  test('deadline hides partial text and aborts even a stalled stream', async () => {
    const stream = summaryStream();
    jest.mocked(summaryFetch).mockResolvedValueOnce(stream.response as never);
    const screen = await open();
    jest.useFakeTimers();
    await search(screen);
    await act(async () => { stream.event('summary', { text: 'Timed partial' }); });
    expect(screen.getByText('Timed partial')).toBeTruthy();
    await act(async () => { jest.advanceTimersByTime(20000); });
    expect(screen.queryByText('Timed partial')).toBeNull();
    expect(jest.mocked(summaryFetch).mock.calls[0][1]!.signal!.aborted).toBe(true);
    jest.useRealTimers();
  });

  test('a first page arriving after leaving Home cannot start a late summary', async () => {
    let resolve!: (value: api.SearchResults) => void;
    jest.mocked(api.searchProjects).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    const screen = await open(); await search(screen);
    await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
    await act(async () => { resolve(results([item()])); });
    await fireEvent.press(screen.getByRole('tab', { name: 'Home' }));
    expect(screen.getByText('compass')).toBeTruthy();
    expect(summaryFetch).not.toHaveBeenCalled();
  });

  test('empty and restored cached results never request a summary', async () => {
    await cache.saveCachedResults('123', results([item()]));
    const screen = await open();
    await waitFor(() => expect(screen.getByText('compass')).toBeTruthy());
    expect(summaryFetch).not.toHaveBeenCalled();
    jest.mocked(api.searchProjects).mockResolvedValueOnce(results([]));
    await search(screen);
    await waitFor(() => expect(screen.queryByText('compass')).toBeNull());
    expect(summaryFetch).not.toHaveBeenCalled();
  });

  test('loading later pages does not request another summary', async () => {
    const stream = summaryStream();
    jest.mocked(summaryFetch).mockResolvedValueOnce(stream.response as never);
    jest.mocked(api.searchProjects).mockResolvedValueOnce(results([item()], 'next')).mockResolvedValueOnce(results([searchSecond]));
    const screen = await open(); await search(screen);
    await waitFor(() => expect(summaryFetch).toHaveBeenCalledTimes(1));
    await fireEvent.press(screen.getByText('Load more'));
    await waitFor(() => expect(screen.getByText('navigator')).toBeTruthy());
    expect(summaryFetch).toHaveBeenCalledTimes(1);
  });
});


describe('spoken summaries', () => {
  const speechKey = 'reporadar.voice.123.readAloud';
  const player = () => jest.mocked(createAudioPlayer).mock.results.at(-1)?.value as unknown as {
    play: jest.Mock; pause: jest.Mock; release: jest.Mock; emit: (status: object) => void;
  };
  beforeEach(() => {
    AppState.currentState = 'active';
    jest.spyOn(AccessibilityInfo, 'isScreenReaderEnabled').mockResolvedValue(false);
  });
  async function complete(screen: Awaited<ReturnType<typeof open>>, voice = true, done: object = { grounded: true, summary_id: 'opaque/id', results: 1 }) {
    const stream = summaryStream();
    jest.mocked(summaryFetch).mockResolvedValueOnce(stream.response as never);
    if (voice) {
      jest.mocked(uploadRecording).mockResolvedValue('voice maps');
      await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressIn');
      await waitFor(() => expect(screen.getByText(/Let go to search/)).toBeTruthy());
      await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressOut');
    } else await search(screen);
    await waitFor(() => expect(stream.reader.read).toHaveBeenCalled());
    await act(async () => { stream.event('summary', { text: 'A useful summary' }); });
    await act(async () => { stream.event('done', done); });
  }
  async function voiceScreen() {
    await AsyncStorage.setItem('reporadar.voice.123.consent', 'yes');
    const screen = await open();
    await waitFor(() => expect(screen.queryByText('Hold the mic to say your idea.')).toBeNull());
    return screen;
  }

  test('voice auto-play uses only the ID URL and bearer header, never a download', async () => {
    const screen = await voiceScreen(); await complete(screen);
    await waitFor(() => expect(createAudioPlayer).toHaveBeenCalledTimes(1));
    expect(createAudioPlayer).toHaveBeenCalledWith({ uri: expect.stringMatching(/\/v1\/voice\/speech\/opaque%2Fid$/), headers: { Authorization: 'Bearer session' } }, { downloadFirst: false });
    expect(setAudioModeAsync).toHaveBeenCalledWith(expect.objectContaining({ playsInSilentMode: false, shouldPlayInBackground: false }));
    expect(player().play).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Stop' })).toBeTruthy();
  });

  test('mic press-in pauses and releases speech before recording starts', async () => {
    const screen = await voiceScreen(); await complete(screen);
    await waitFor(() => expect(createAudioPlayer).toHaveBeenCalled());
    const speaking = player();
    // The first recorder belongs to the completed voice search; inspect the new hold.
    await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressIn');
    await waitFor(() => expect(screen.getByText(/Let go to search/)).toBeTruthy());
    // eslint-disable-next-line import/namespace
    const recorder = jest.mocked(AudioModule.AudioRecorder).mock.results.at(-1)!.value;
    expect(speaking.pause).toHaveBeenCalledTimes(1);
    expect(speaking.release).toHaveBeenCalledTimes(1);
    expect(speaking.pause.mock.invocationCallOrder[0]).toBeLessThan(recorder.record.mock.invocationCallOrder[0]);
    expect(speaking.release.mock.invocationCallOrder[0]).toBeLessThan(recorder.record.mock.invocationCallOrder[0]);
  });

  test('typed summary never auto-plays but Read aloud works and Stop releases', async () => {
    const screen = await open(); await complete(screen, false);
    expect(createAudioPlayer).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByRole('button', { name: 'Read aloud' }));
    await waitFor(() => expect(createAudioPlayer).toHaveBeenCalled());
    await fireEvent.press(screen.getByRole('button', { name: 'Stop' }));
    expect(player().pause).toHaveBeenCalled(); expect(player().release).toHaveBeenCalled();
    expect(screen.getByText('A useful summary')).toBeTruthy();
  });

  test.each(['setting off', 'screen reader', 'inactive', 'ungrounded', 'missing ID'])('%s prevents automatic speech', async condition => {
    if (condition === 'setting off') await AsyncStorage.setItem(speechKey, 'false');
    if (condition === 'screen reader') jest.mocked(AccessibilityInfo.isScreenReaderEnabled).mockResolvedValue(true);
    if (condition === 'inactive') AppState.currentState = 'inactive';
    const screen = await voiceScreen();
    await complete(screen, true, condition === 'ungrounded' ? { grounded: false } : condition === 'missing ID' ? { grounded: true, results: 1 } : undefined);
    expect(createAudioPlayer).not.toHaveBeenCalled();
    if (condition === 'missing ID') expect(screen.queryByRole('button', { name: 'Read aloud' })).toBeNull();
    if (condition === 'setting off') {
      await fireEvent.press(screen.getByRole('button', { name: 'Read aloud' }));
      await waitFor(() => expect(createAudioPlayer).toHaveBeenCalledTimes(1));
    }
  });

  test.each(['new search', 'tab', 'sign-out', 'background', 'unmount'])('%s stops and releases playback', async action => {
    let changed: (state: AppStateStatus) => void = () => {};
    jest.spyOn(AppState, 'addEventListener').mockImplementation((_, fn) => { const old = changed; changed = state => { old(state); fn(state); }; return { remove: jest.fn() }; });
    const screen = await voiceScreen(); await complete(screen);
    await waitFor(() => expect(createAudioPlayer).toHaveBeenCalled());
    const playing = player();
    if (action === 'new search') await search(screen, 'new search');
    else if (action === 'background') await act(async () => { changed('background'); });
    else if (action === 'unmount') await screen.unmount();
    else {
      await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
      if (action === 'sign-out') await fireEvent.press(screen.getByText('Sign out'));
    }
    expect(playing.pause).toHaveBeenCalled(); expect(playing.release).toHaveBeenCalledTimes(1);
  });

  test('speech failure leaves the summary and does not retry', async () => {
    const screen = await voiceScreen(); await complete(screen);
    await waitFor(() => expect(createAudioPlayer).toHaveBeenCalled());
    await act(async () => { player().emit({ error: '503 speech_unavailable' }); });
    expect(screen.getByText('A useful summary')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeTruthy();
    expect(player().release).toHaveBeenCalledTimes(1); expect(createAudioPlayer).toHaveBeenCalledTimes(1);
  });

  test('auto-play tip appears only once per account after playback starts', async () => {
    const screen = await voiceScreen(); await complete(screen);
    await waitFor(() => expect(createAudioPlayer).toHaveBeenCalled());
    expect(screen.queryByText('Turn this off in Profile › Voice')).toBeNull();
    await act(async () => { player().emit({ playing: true }); });
    expect(screen.getByText('Turn this off in Profile › Voice')).toBeTruthy();
    await act(async () => { player().emit({ didJustFinish: true }); });
    expect(screen.getByText('Turn this off in Profile › Voice')).toBeTruthy();
    await complete(screen);
    await waitFor(() => expect(createAudioPlayer).toHaveBeenCalledTimes(2));
    await act(async () => { player().emit({ playing: true }); });
    expect(screen.queryByText('Turn this off in Profile › Voice')).toBeNull();
  });

  test('read-aloud setting persists per account and is cleared on sign-out', async () => {
    const screen = await open();
    await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
    await fireEvent.press(screen.getByText('Voice'));
    const control = screen.getByRole('switch', { name: 'Read summaries aloud' });
    expect(control.props.value).toBe(true);
    await fireEvent(control, 'valueChange', false);
    await waitFor(async () => expect(await AsyncStorage.getItem(speechKey)).toBe('false'));
    await screen.unmount();
    const again = await open();
    await fireEvent.press(again.getByRole('tab', { name: 'Profile' }));
    await fireEvent.press(again.getByText('Voice'));
    await waitFor(() => expect(again.getByRole('switch', { name: 'Read summaries aloud' }).props.value).toBe(false));
    await fireEvent.press(again.getByText('Back to Profile'));
    await fireEvent.press(again.getByText('Sign out'));
    await waitFor(async () => expect(await AsyncStorage.getItem(speechKey)).toBeNull());
    await again.unmount();
    const other = await open({ user: { github_id: 456, login: 'other' } });
    await fireEvent.press(other.getByRole('tab', { name: 'Profile' })); await fireEvent.press(other.getByText('Voice'));
    expect(other.getByRole('switch', { name: 'Read summaries aloud' }).props.value).toBe(true);
  });
});

describe('automatic search retries', () => {
  beforeEach(() => { AppState.currentState = 'active'; });
  afterEach(() => { jest.useRealTimers(); });
  const starting = (seconds?: number, code = 'SEARCH_UNAVAILABLE') => Object.assign(
    new api.DiscoveryApiError('Search is starting or unavailable. Try again shortly.', 503, code, true),
    { retryAfterSeconds: seconds },
  );
  const advance = async (ms: number) => { await act(async () => { jest.advanceTimersByTime(ms); }); };
  const setup = async () => {
    const screen = await open();
    jest.useFakeTimers({ doNotFake: ['setImmediate', 'nextTick'] });
    return screen;
  };

  test.each([1, 2, 3])('%s startup failures keep the button disabled until final outcome', async failures => {
    const screen = await setup();
    for (let i = 0; i < failures; i++) jest.mocked(api.searchProjects).mockRejectedValueOnce(starting());
    jest.mocked(api.searchProjects).mockResolvedValue(results([item()]));
    await search(screen);
    expect(screen.getByRole('button', { name: 'Search projects' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull();
    expect(screen.getByLabelText('Search is starting…')).toBeTruthy();
    await advance(1999);
    expect(api.searchProjects).toHaveBeenCalledTimes(1);
    await advance(1);
    if (failures > 1) {
      expect(screen.getByRole('button', { name: 'Search projects' })).toBeDisabled();
      await advance(3999);
      expect(api.searchProjects).toHaveBeenCalledTimes(2);
      await advance(1);
    }
    expect(api.searchProjects).toHaveBeenCalledTimes(Math.min(failures + 1, 3));
    expect(screen.getByRole('button', { name: 'Search projects' })).not.toBeDisabled();
    if (failures === 3) expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
    else { expect(screen.getByText('compass')).toBeTruthy(); expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull(); }
    await advance(30000);
    expect(api.searchProjects).toHaveBeenCalledTimes(Math.min(failures + 1, 3));
  });

  test.each([[3, 3000], [999, 10000], [0, 1000]])('Retry-After %s waits %s ms', async (seconds, delay) => {
    const screen = await setup();
    jest.mocked(api.searchProjects).mockRejectedValueOnce(starting(seconds));
    await search(screen); await advance(delay - 1);
    expect(api.searchProjects).toHaveBeenCalledTimes(1);
    await advance(1); expect(api.searchProjects).toHaveBeenCalledTimes(2);
    expect(jest.mocked(api.searchProjects).mock.calls[1]).toEqual(jest.mocked(api.searchProjects).mock.calls[0]);
  });

  test('SEARCH_INCOMPLETE retries quietly', async () => {
    const screen = await setup();
    jest.mocked(api.searchProjects).mockRejectedValueOnce(starting(undefined, 'SEARCH_INCOMPLETE'));
    await search(screen); await advance(2000);
    expect(api.searchProjects).toHaveBeenCalledTimes(2); expect(screen.getByText('compass')).toBeTruthy();
  });

  test.each([
    new api.DiscoveryApiError('Limited', 429, 'SEARCH_INCOMPLETE', true),
    new api.DiscoveryApiError('Sign in', 401), new api.DiscoveryApiError('Forbidden', 403),
    new api.DiscoveryApiError('Not configured', 503, 'SEARCH_UNAVAILABLE', false),
    new api.DiscoveryApiError('Busy', 503, 'SEARCH_BUSY', true),
    new api.DiscoveryNetworkError('Offline'),
  ])('does not retry %s', async failure => {
    const screen = await setup(); jest.mocked(api.searchProjects).mockRejectedValueOnce(failure);
    await search(screen); await advance(30000); expect(api.searchProjects).toHaveBeenCalledTimes(1);
  });

  test('degraded results remain visible without retry', async () => {
    const screen = await setup();
    jest.mocked(api.searchProjects).mockResolvedValueOnce(results([item()], null, { degraded: true }));
    await search(screen); await advance(30000);
    expect(api.searchProjects).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Some sources were unavailable. Results may be incomplete.')).toBeTruthy();
  });

  test('a stale Retry handler cannot start a second search', async () => {
    const screen = await setup();
    jest.mocked(api.searchProjects).mockRejectedValueOnce(new api.DiscoveryNetworkError('Offline'));
    await search(screen);
    const retryButton = screen.getByRole('button', { name: 'Try again' });
    const retry = () => fireEvent.press(retryButton);
    let resolve!: (data: api.SearchResults) => void;
    jest.mocked(api.searchProjects).mockReturnValueOnce(new Promise(done => { resolve = done; }));
    await retry();
    await retry();
    expect(api.searchProjects).toHaveBeenCalledTimes(2);
    await act(async () => { resolve(results([])); });
  });

  test('repeated refresh during a retry wait cannot start a second search', async () => {
    const screen = await setup(); await search(screen);
    const refresh = screen.getByTestId('discovery-list').props.refreshControl.props.onRefresh;
    jest.mocked(api.searchProjects).mockRejectedValueOnce(starting());
    await act(async () => { refresh(); });
    await act(async () => { refresh(); refresh(); });
    expect(api.searchProjects).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: 'Search projects' })).toBeDisabled();
    await advance(2000);
    expect(api.searchProjects).toHaveBeenCalledTimes(3);
  });

  test.each(['unmount', 'sign-out', 'background', 'tab', 'session', 'account'])('%s cancels a retry wait', async action => {
    let changed = (_: AppStateStatus) => {};
    jest.spyOn(AppState, 'addEventListener').mockImplementation((_, listener) => {
      const previous = changed; changed = state => { previous(state); listener(state); }; return { remove: jest.fn() };
    });
    const screen = await setup(); jest.mocked(api.searchProjects).mockRejectedValueOnce(starting());
    await search(screen);
    if (action === 'unmount') await screen.unmount();
    else if (action === 'background') await act(async () => { changed('background'); });
    else if (action === 'account' || action === 'session') await screen.rerender(
      <AppProvider><DiscoveryScreen token={action === 'session' ? 'new-session' : 'session'} user={action === 'account' ? { login: 'other', github_id: 999 } : user} onSignOut={jest.fn()} signingOut={false} accountError="" onUnauthorized={jest.fn()} /></AppProvider>,
    );
    else {
      await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
      if (action === 'sign-out') await fireEvent.press(screen.getByText('Sign out'));
    }
    await advance(30000); expect(api.searchProjects).toHaveBeenCalledTimes(1);
    expect(await cache.loadCachedResults('123')).toBeNull();
    if (['background', 'tab'].includes(action)) {
      if (action === 'background') await act(async () => { changed('active'); });
      else await fireEvent.press(screen.getByRole('tab', { name: 'Home' }));
      expect(screen.getByText('Search was interrupted. Try again.')).toBeTruthy();
      expect(screen.getByRole('button', { name: 'Search projects' })).not.toBeDisabled();
      await fireEvent.press(screen.getByRole('button', { name: 'Try again' }));
      expect(api.searchProjects).toHaveBeenCalledTimes(2);
    } else {
      expect(screen.queryByText('Search was interrupted. Try again.')).toBeNull();
    }
  });

  test('typing during a search or retry wait neither cancels nor unlocks it', async () => {
    const screen = await setup();
    jest.mocked(api.searchProjects).mockRejectedValueOnce(starting());
    await search(screen);
    await fireEvent.changeText(screen.getByLabelText('Project idea'), 'changed idea');
    expect(screen.getByRole('button', { name: 'Search projects' })).toBeDisabled();
    await fireEvent.press(screen.getByRole('button', { name: 'Search projects' }));
    expect(api.searchProjects).toHaveBeenCalledTimes(1);
    await advance(2000);
    expect(api.searchProjects).toHaveBeenCalledTimes(2);
    expect(jest.mocked(api.searchProjects).mock.calls[1]).toEqual(jest.mocked(api.searchProjects).mock.calls[0]);
    expect(screen.getByText('compass')).toBeTruthy();
    expect(screen.getByLabelText('Project idea').props.value).toBe('changed idea');
  });

  test('leaving Home during the first request keeps its results', async () => {
    const screen = await setup();
    let finish!: (data: api.SearchResults) => void;
    jest.mocked(api.searchProjects).mockReturnValueOnce(new Promise(done => { finish = done; }));
    await search(screen);
    await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
    await act(async () => { finish(results([item()])); });
    await fireEvent.press(screen.getByRole('tab', { name: 'Home' }));
    expect(screen.getByText('compass')).toBeTruthy();
    expect(screen.queryByText('Search was interrupted. Try again.')).toBeNull();
  });

  // The ref only refreshes in the layout effect, so a 503 that lands between a
  // tab press and the re-render used to still read tab === 'Home' and retry.
  test('a 503 in the same act as the tab press is interrupted, not retried', async () => {
    const screen = await setup();
    let fail!: (failure: unknown) => void;
    jest.mocked(api.searchProjects).mockReturnValueOnce(new Promise((_, reject) => { fail = reject; }));
    await search(screen);
    await act(async () => {
      // Not awaited: awaiting the press would let the layout effect refresh the
      // ref before the rejection lands, hiding the race this test pins.
      fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
      fail(starting());
      await Promise.resolve();
    });
    await advance(30000);
    expect(api.searchProjects).toHaveBeenCalledTimes(1);
    await fireEvent.press(screen.getByRole('tab', { name: 'Home' }));
    expect(screen.getByText('Search was interrupted. Try again.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Search projects' })).not.toBeDisabled();
  });

  test('a retryable 503 while already off Home is interrupted, not retried', async () => {
    const screen = await setup();
    let fail!: (failure: unknown) => void;
    jest.mocked(api.searchProjects).mockReturnValueOnce(new Promise((_, reject) => { fail = reject; }));
    await search(screen);
    await fireEvent.press(screen.getByRole('tab', { name: 'Profile' }));
    await act(async () => { fail(starting()); });
    await advance(30000);
    expect(api.searchProjects).toHaveBeenCalledTimes(1);
    await fireEvent.press(screen.getByRole('tab', { name: 'Home' }));
    expect(screen.getByText('Search was interrupted. Try again.')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Try again' }));
    await act(async () => {});
    expect(api.searchProjects).toHaveBeenCalledTimes(2);
  });

  test('a 503 in the same act as opening details is interrupted, not retried', async () => {
    const screen = await setup();
    await search(screen);
    expect(screen.getByText('compass')).toBeTruthy();
    let fail!: (failure: unknown) => void;
    jest.mocked(api.searchProjects).mockReturnValueOnce(new Promise((_, reject) => { fail = reject; }));
    const refresh = screen.getByTestId('discovery-list').props.refreshControl.props.onRefresh;
    await act(async () => { refresh(); });
    await act(async () => {
      await fireEvent.press(screen.getByRole('button', { name: 'Open octocat/compass' }));
      fail(starting());
      await Promise.resolve();
    });
    await advance(30000);
    expect(api.searchProjects).toHaveBeenCalledTimes(2);
    await fireEvent.press(screen.getByRole('button', { name: 'Go back' }));
    expect(screen.getByText('Search was interrupted. Try again.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
  });

  test('a 503 then 200 on Home still succeeds quietly', async () => {
    const screen = await setup();
    jest.mocked(api.searchProjects).mockRejectedValueOnce(starting()).mockResolvedValueOnce(results([item()]));
    await search(screen);
    expect(screen.getByRole('button', { name: 'Search projects' })).toBeDisabled();
    await advance(1999);
    expect(api.searchProjects).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Search projects' })).toBeDisabled();
    await advance(1);
    await act(async () => {});
    expect(api.searchProjects).toHaveBeenCalledTimes(2);
    expect(screen.getByText('compass')).toBeTruthy();
    expect(screen.queryByText('Search was interrupted. Try again.')).toBeNull();
    expect(screen.getByRole('button', { name: 'Search projects' })).not.toBeDisabled();
  });

  test.each([null, 'unknown'])('AppState %s at launch still allows searching', async state => {
    AppState.currentState = state as unknown as AppStateStatus;
    const screen = await setup();
    await search(screen);
    expect(api.searchProjects).toHaveBeenCalledTimes(1);
  });
});


test('a voice transcript during a pending search does not launch or queue another search', async () => {
  await AsyncStorage.setItem('reporadar.voice.123.consent', 'yes');
  jest.mocked(uploadRecording).mockResolvedValue('voice maps');
  let finish!: (data: api.SearchResults) => void;
  jest.mocked(api.searchProjects).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  const screen = await open();
  await waitFor(() => expect(screen.queryByText('Hold the mic to say your idea.')).toBeNull());
  await search(screen);
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressIn');
  await waitFor(() => expect(screen.getByText(/Let go to search/)).toBeTruthy());
  await fireEvent(screen.getByLabelText('Hold to record your idea'), 'pressOut');
  await waitFor(() => expect(uploadRecording).toHaveBeenCalled());
  expect(api.searchProjects).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(screen.getByLabelText('Project idea').props.value).toBe('voice maps'));
  await act(async () => { finish(results([])); });
  expect(api.searchProjects).toHaveBeenCalledTimes(1);
});
