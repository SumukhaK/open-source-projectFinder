import AsyncStorage from '@react-native-async-storage/async-storage';
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

beforeEach(async () => {
  await AsyncStorage.clear();
});

test('cached results and favourites are isolated per account', async () => {
  await saveCachedResults('123', results);
  await saveCachedFavourites('123', [project]);

  expect((await loadCachedResults('123'))?.data).toEqual(results);
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
  expect((await loadCachedResults('456'))?.data).toEqual(results);
});

test('malformed or stale cache entries are ignored instead of trusted', async () => {
  await AsyncStorage.setItem('reporadar.discovery.123.results', '{not-json');
  await AsyncStorage.setItem('reporadar.discovery.123.favourites', JSON.stringify({ items: [{ ...project, stars: 'many' }] }));

  expect(await loadCachedResults('123')).toBeNull();
  expect(await loadCachedFavourites('123')).toBeNull();
});
