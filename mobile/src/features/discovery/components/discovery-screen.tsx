import React, { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BrandLoader } from '../../../components/brand-loader';
import { BrandMark } from '../../../components/brand-mark';
import { getThemeColors } from '../../../config/branding';
import { discoveryConfig } from '../../../config/discovery';
import { useTheme } from '../../../lib/theme';
import {
  DiscoveryApiError,
  DiscoveryNetworkError,
  DiscoveryResponseError,
  getFavourites,
  getProject,
  Project,
  ProjectDetails,
  removeFavourite,
  saveFavourite,
  searchProjects,
  SearchResults,
} from '../api/discovery';
import {
  clearDiscoveryCache,
  loadCachedFavourites,
  loadCachedResults,
  saveCachedFavourites,
  saveCachedResults,
} from '../cache';
import { ProjectCard } from './project-card';
import { ProjectDetailsView } from './project-details';

export type DiscoveryUser = { github_id?: number; login: string; avatar_url?: string };
type Props = {
  token: string;
  user: DiscoveryUser;
  onSignOut: () => void;
  signingOut: boolean;
  accountError: string;
  onUnauthorized: () => void;
};

const accountKey = (user: DiscoveryUser) => String(user.github_id ?? user.login);

export function DiscoveryScreen({ token, user, onSignOut, signingOut, accountError, onUnauthorized }: Props) {
  const { mode } = useTheme();
  const colors = getThemeColors(mode);
  const account = accountKey(user);
  const previousAccount = useRef(account);
  const lastIdea = useRef('');
  const [tab, setTab] = useState<'Discover' | 'Favourites'>('Discover');
  const [idea, setIdea] = useState('');
  const [results, setResults] = useState<SearchResults | null>(null);
  const [favourites, setFavourites] = useState<Project[]>([]);
  const [error, setError] = useState('');
  const [favouritesError, setFavouritesError] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selected, setSelected] = useState<Project | null>(null);
  const [details, setDetails] = useState<ProjectDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState('');
  const [favouriteBusy, setFavouriteBusy] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (previousAccount.current !== account) {
      const previous = previousAccount.current;
      previousAccount.current = account;
      setResults(null);
      setFavourites([]);
      setSelected(null);
      setDetails(null);
      setIdea('');
      setError('');
      setFavouritesError('');
      void clearDiscoveryCache(previous);
    }
    void (async () => {
      const [cachedResults, cachedFavourites] = await Promise.all([
        loadCachedResults(account),
        loadCachedFavourites(account),
      ]);
      if (!active) return;
      if (cachedResults) setResults(cachedResults.data);
      if (cachedFavourites) setFavourites(cachedFavourites.data);
      try {
        const data = await getFavourites(token);
        if (!active) return;
        setFavourites(data.items);
        await saveCachedFavourites(account, data.items);
      } catch (failure) {
        if (!active) return;
        if (failure instanceof DiscoveryApiError && failure.status === 401) {
          void clearDiscoveryCache(account);
          onUnauthorized();
          return;
        }
        setFavouritesError('Unable to refresh favourites. Please try again.');
      }
    })();
    return () => { active = false; };
  }, [account, token, onUnauthorized]);

  const failureMessage = (failure: unknown, fallback: string): string | null => {
    if (failure instanceof DiscoveryApiError) {
      if (failure.status === 401) {
        void clearDiscoveryCache(account);
        onUnauthorized();
        return null;
      }
      return failure.message;
    }
    if (failure instanceof DiscoveryNetworkError || failure instanceof DiscoveryResponseError) return failure.message;
    return fallback;
  };

  const submit = async () => {
    const text = idea.trim();
    if (text.length < discoveryConfig.minIdeaLength || text.length > discoveryConfig.maxIdeaLength) {
      setError('Describe your idea');
      return;
    }
    lastIdea.current = text;
    setLoading(true);
    setError('');
    setResults(null);
    try {
      const data = await searchProjects(token, { idea: text, page: 1 });
      setResults(data);
      await saveCachedResults(account, data);
    } catch (failure) {
      const message = failureMessage(failure, 'Search failed. Please try again.');
      if (message) setError(message);
    } finally {
      setLoading(false);
    }
  };

  const loadMore = async () => {
    if (!results || loadingMore) return;
    setLoadingMore(true);
    setError('');
    try {
      const data = await searchProjects(token, { idea: lastIdea.current, page: results.page + 1 });
      const combined = { ...data, items: [...results.items, ...data.items] };
      setResults(combined);
      await saveCachedResults(account, combined);
    } catch (failure) {
      const message = failureMessage(failure, 'Unable to load more results. Please try again.');
      if (message) setError(message);
    } finally {
      setLoadingMore(false);
    }
  };

  const isSaved = (fullName: string) => favourites.some(item => item.full_name === fullName);

  const toggleFavourite = async (project: Project) => {
    if (favouriteBusy) return;
    const saved = isSaved(project.full_name);
    const previous = favourites;
    const next = saved
      ? previous.filter(item => item.full_name !== project.full_name)
      : [project, ...previous];
    setFavouriteBusy(project.full_name);
    setFavouritesError('');
    setFavourites(next);
    try {
      if (saved) await removeFavourite(token, project.full_name);
      else await saveFavourite(token, project.full_name);
      await saveCachedFavourites(account, next);
    } catch (failure) {
      setFavourites(previous);
      if (failure instanceof DiscoveryApiError && failure.status === 401) {
        void clearDiscoveryCache(account);
        onUnauthorized();
        return;
      }
      setFavouritesError('Unable to update favourites. Please try again.');
    } finally {
      setFavouriteBusy(null);
    }
  };

  const openDetails = async (project: Project) => {
    setSelected(project);
    setDetails(null);
    setDetailsError('');
    setDetailsLoading(true);
    try {
      setDetails(await getProject(token, project.full_name));
    } catch (failure) {
      const message = failureMessage(failure, 'Unable to load this project. Please try again.');
      if (message) setDetailsError(message);
    } finally {
      setDetailsLoading(false);
    }
  };

  const leave = async () => {
    await clearDiscoveryCache(account);
    onSignOut();
  };

  const canLoadMore = results !== null
    && results.items.length > 0
    && results.items.length < results.total
    && results.page < discoveryConfig.maxPage;

  return <SafeAreaView style={[styles.root, { backgroundColor: colors.background }]}>
    <View style={[styles.header, { borderColor: colors.border }]}>
      <BrandMark mode={mode} size={38} />
      <View style={styles.headerText}>
        <Text accessibilityRole="header" style={[styles.title, { color: colors.text }]}>Discover projects</Text>
        <Text style={[styles.meta, { color: colors.muted }]}>@{user.login}</Text>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ disabled: signingOut }}
        disabled={signingOut}
        onPress={() => void leave()}
        style={[styles.signOut, { borderColor: colors.border }]}
      >
        <Text style={{ color: colors.text }}>{signingOut ? 'Signing out' : 'Sign out'}</Text>
      </Pressable>
    </View>
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      {accountError ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.error, { color: colors.text }]}>{accountError}</Text> : null}
      {favouritesError ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.error, { color: colors.text }]}>{favouritesError}</Text> : null}
      {selected ? <ProjectDetailsView
        project={selected}
        details={details}
        loading={detailsLoading}
        error={detailsError}
        saved={isSaved(selected.full_name)}
        busy={favouriteBusy === selected.full_name}
        onBack={() => { setSelected(null); setDetails(null); setDetailsError(''); }}
        onToggle={() => void toggleFavourite(selected)}
      /> : <>
        <View style={styles.tabs}>
          {(['Discover', 'Favourites'] as const).map(name => <Pressable
            key={name}
            accessibilityRole="tab"
            accessibilityState={{ selected: tab === name }}
            onPress={() => setTab(name)}
            style={[styles.tab, { backgroundColor: tab === name ? colors.accent : colors.surface, borderColor: colors.border }]}
          >
            <Text style={{ color: tab === name ? colors.onAccent : colors.text, fontWeight: '600' }}>{name}</Text>
          </Pressable>)}
        </View>
        {tab === 'Discover' ? <>
          <TextInput
            accessibilityLabel="Project idea"
            placeholder="Describe your idea"
            placeholderTextColor={colors.muted}
            value={idea}
            onChangeText={setIdea}
            maxLength={discoveryConfig.maxIdeaLength}
            multiline
            style={[styles.input, { backgroundColor: colors.surface, borderColor: colors.border, color: colors.text }]}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: loading }}
            disabled={loading}
            onPress={() => void submit()}
            style={[styles.search, { backgroundColor: colors.accent, opacity: loading ? 0.6 : 1 }]}
          >
            <Text style={[styles.searchText, { color: colors.onAccent }]}>Search projects</Text>
          </Pressable>
          {loading ? <BrandLoader mode={mode} label="Searching GitHub" /> : null}
          {error ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.error, { color: colors.text }]}>{error}</Text> : null}
          {results?.incomplete ? <Text style={[styles.notice, { color: colors.text }]}>Results may be partial. GitHub returned an incomplete set.</Text> : null}
          {results && results.items.length === 0 && !results.incomplete ? <Text style={[styles.notice, { color: colors.muted }]}>No projects matched your idea. Try different keywords.</Text> : null}
          {results?.items.map(project => <ProjectCard
            key={project.full_name}
            project={project}
            saved={isSaved(project.full_name)}
            busy={favouriteBusy === project.full_name}
            onOpen={() => void openDetails(project)}
            onToggle={() => void toggleFavourite(project)}
          />)}
          {canLoadMore ? <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: loadingMore }}
            disabled={loadingMore}
            onPress={() => void loadMore()}
            style={[styles.more, { borderColor: colors.border }]}
          >
            <Text style={{ color: colors.text }}>{loadingMore ? 'Loading more' : 'Load more'}</Text>
          </Pressable> : null}
        </> : <>
          {favourites.length === 0 ? <Text style={[styles.notice, { color: colors.muted }]}>No favourites yet.</Text> : null}
          {favourites.map(project => <ProjectCard
            key={project.full_name}
            project={project}
            saved
            busy={favouriteBusy === project.full_name}
            onOpen={() => void openDetails(project)}
            onToggle={() => void toggleFavourite(project)}
          />)}
        </>}
      </>}
    </ScrollView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  headerText: { flex: 1 },
  title: { fontSize: 22, lineHeight: 28, fontWeight: '700' },
  signOut: { minHeight: 44, paddingHorizontal: 12, borderWidth: 1, borderRadius: 12, justifyContent: 'center' },
  content: { padding: 20, gap: 14, width: '100%', maxWidth: 720, alignSelf: 'center' },
  tabs: { flexDirection: 'row', gap: 10 },
  tab: { flex: 1, minHeight: 46, borderWidth: 1, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  input: { minHeight: 92, borderWidth: 1, borderRadius: 14, padding: 14, fontSize: 16, lineHeight: 24, textAlignVertical: 'top' },
  search: { minHeight: 50, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  searchText: { fontSize: 16, fontWeight: '600' },
  error: { fontSize: 15, lineHeight: 23 },
  notice: { fontSize: 15, lineHeight: 23 },
  more: { minHeight: 48, borderWidth: 1, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  meta: { fontSize: 13, lineHeight: 20 },
});
