import AsyncStorage from '@react-native-async-storage/async-storage';
import { z } from 'zod';
import { discoveryConfig } from '../../config/discovery';
import { Project, projectSchema, SearchResults, searchResultsSchema } from './api/discovery';

export type Cached<T> = { data: T; savedAt: number };

// v2 is the hybrid /v1 results snapshot; v1 legacy page-based snapshots lack
// this field and fail the schema, so they are dropped instead of rendered.
const RESULTS_CACHE_VERSION = 2;
const resultsCacheSchema = z.object({
  version: z.literal(RESULTS_CACHE_VERSION),
  data: searchResultsSchema,
  savedAt: z.number(),
});
const favouritesCacheSchema = z.object({ data: z.array(projectSchema), savedAt: z.number() });

const resultsKey = (account: string) => `${discoveryConfig.cachePrefix}.${account}.results`;
const favouritesKey = (account: string) => `${discoveryConfig.cachePrefix}.${account}.favourites`;

async function load<T>(key: string, schema: z.ZodType<Cached<T>>): Promise<Cached<T> | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    if (!raw) return null;
    const parsed = schema.safeParse(JSON.parse(raw));
    if (parsed.success) return parsed.data;
    // An incompatible snapshot is removed so it cannot be restored later.
    await AsyncStorage.removeItem(key);
    return null;
  } catch {
    // A corrupt or unreadable cache must never block discovery.
    return null;
  }
}

async function save<T>(key: string, data: T, version?: number) {
  try {
    const envelope = version === undefined
      ? { data, savedAt: Date.now() }
      : { version, data, savedAt: Date.now() };
    await AsyncStorage.setItem(key, JSON.stringify(envelope));
  } catch {
    // Cache writes are best effort; the current session state remains usable.
  }
}

export async function loadCachedResults(account: string): Promise<Cached<SearchResults> | null> {
  const cached = await load<SearchResults>(resultsKey(account), resultsCacheSchema);
  if (!cached) return null;
  // Cursors are session-scoped: a restored page never resumes an old cursor.
  return { ...cached, data: { ...cached.data, next_cursor: null } };
}
export const saveCachedResults = (account: string, results: SearchResults) =>
  save(resultsKey(account), { ...results, next_cursor: null }, RESULTS_CACHE_VERSION);
export const loadCachedFavourites = (account: string) =>
  load<Project[]>(favouritesKey(account), favouritesCacheSchema);
export const saveCachedFavourites = (account: string, favourites: Project[]) =>
  save(favouritesKey(account), favourites);

export async function clearDiscoveryCache(account: string) {
  try {
    await AsyncStorage.multiRemove([resultsKey(account), favouritesKey(account)]);
  } catch {
    // Sign-out and account switching still proceed if storage is unavailable.
  }
}
