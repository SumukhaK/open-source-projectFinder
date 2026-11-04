import AsyncStorage from '@react-native-async-storage/async-storage';
import type { SearchItem, SearchResults } from '../src/features/discovery/api/discovery';
import {
  clearDiscoveryCache,
  loadCachedFavourites,
  loadCachedResults,
  saveCachedFavourites,
  saveCachedResults,
} from '../src/features/discovery/cache';

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
const item: SearchItem = {
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
const results: SearchResults = {
  items: [item],
  next_cursor: 'cursor-secret',
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
const resultsKey = 'reporadar.discovery.123.results';

beforeEach(async () => {
  await AsyncStorage.clear();
});

test('cached results and favourites are isolated per account', async () => {
  await saveCachedResults('123', results);
  await saveCachedFavourites('123', [project]);

  expect((await loadCachedResults('123'))?.data.items[0].name).toBe('compass');
  expect((await loadCachedFavourites('123'))?.data).toEqual([project]);
  expect(await loadCachedResults('456')).toBeNull();
  expect(await loadCachedFavourites('456')).toBeNull();
});

test('clearing one account leaves another account cache intact', async () => {
  await saveCachedResults('123', results);
  await saveCachedFavourites('123', [project]);
  await saveCachedResults('456', results);

  await clearDiscoveryCache('123');

  expect(await loadCachedResults('123')).toBeNull();
  expect(await loadCachedFavourites('123')).toBeNull();
  expect((await loadCachedResults('456'))?.data.items[0].name).toBe('compass');
});

test('malformed cache entries are ignored instead of trusted', async () => {
  await AsyncStorage.setItem(resultsKey, '{not-json');
  await AsyncStorage.setItem('reporadar.discovery.123.favourites', JSON.stringify({ items: [{ ...project, stars: 'many' }] }));

  expect(await loadCachedResults('123')).toBeNull();
  expect(await loadCachedFavourites('123')).toBeNull();
});

test('a legacy results snapshot is dropped without touching favourites', async () => {
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
  await AsyncStorage.setItem(resultsKey, JSON.stringify({ data: legacy, savedAt: 1 }));
  await saveCachedFavourites('123', [project]);

  expect(await loadCachedResults('123')).toBeNull();
  expect(await AsyncStorage.getItem(resultsKey)).toBeNull();
  expect((await loadCachedFavourites('123'))?.data).toEqual([project]);
});

test('the cursor is never written to storage and is cleared when results are restored', async () => {
  await saveCachedResults('123', results);

  const raw = await AsyncStorage.getItem(resultsKey);
  expect(raw).not.toContain('cursor-secret');
  expect(JSON.parse(raw ?? '{}').version).toBe(2);

  const restored = await loadCachedResults('123');
  expect(restored?.data.next_cursor).toBeNull();
  expect(restored?.data.has_more).toBe(true);
});
