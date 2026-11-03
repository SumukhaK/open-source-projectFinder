import AsyncStorage from '@react-native-async-storage/async-storage';
import { z } from 'zod';
import { discoveryConfig } from '../../config/discovery';
import { Project, projectSchema, SearchResults, searchResultsSchema } from './api/discovery';

export type Cached<T> = { data: T; savedAt: number };

const resultsCacheSchema = z.object({ data: searchResultsSchema, savedAt: z.number() });
const favouritesCacheSchema = z.object({ data: z.array(projectSchema), savedAt: z.number() });

const resultsKey = (account: string) => `${discoveryConfig.cachePrefix}.${account}.results`;
const favouritesKey = (account: string) => `${discoveryConfig.cachePrefix}.${account}.favourites`;

async function load<T>(key: string, schema: z.ZodType<Cached<T>>): Promise<Cached<T> | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    if (!raw) return null;
    const parsed = schema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : null;
  } catch {
    // A corrupt or unreadable cache must never block discovery.
    return null;
  }
}

async function save<T>(key: string, data: T) {
  try {
    await AsyncStorage.setItem(key, JSON.stringify({ data, savedAt: Date.now() }));
  } catch {
    // Cache writes are best effort; the current session state remains usable.
  }
}

export const loadCachedResults = (account: string) =>
  load<SearchResults>(resultsKey(account), resultsCacheSchema);
export const saveCachedResults = (account: string, results: SearchResults) =>
  save(resultsKey(account), results);
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
