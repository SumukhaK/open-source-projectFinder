import React, { useEffect, useRef, useState } from 'react';
import { Image, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { AppearanceControls } from '../../../components/appearance-controls';
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
  SourceHealth,
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

const healthy = (source: SourceHealth) => source.status === 'ok' && !source.incomplete;

// One bounded line naming which source is missing; never raw backend reasons.
function sourceDetail(results: SearchResults): string | null {
  const github = healthy(results.sources.github);
  const archive = healthy(results.sources.archive);
  if (github && !archive) return 'The project archive did not respond, so only live GitHub results are shown.';
  if (!github && archive) return 'Live GitHub search did not respond, so only archive results are shown.';
  if (!github && !archive) return 'Neither live GitHub search nor the project archive responded fully.';
  return null;
}

const completeSearch = (results: SearchResults) =>
  !results.degraded && healthy(results.sources.github) && healthy(results.sources.archive);

export function DiscoveryScreen({ token, user, onSignOut, signingOut, accountError, onUnauthorized }: Props) {
  const { mode } = useTheme();
  const colors = getThemeColors(mode);
  const account = accountKey(user);
  const previousAccount = useRef(account);
  const listSeq = useRef(0);
  const detailsSeq = useRef(0);
  // Bumped on sign-out and unmount so late responses never write the cache.
  const sessionSeq = useRef(0);
  const [tab, setTab] = useState<'Home' | 'Profile'>('Home');
  const [idea, setIdea] = useState('');
  const [activeIdea, setActiveIdea] = useState('');
  const [fromCache, setFromCache] = useState(false);
  const [results, setResults] = useState<SearchResults | null>(null);
  const [favourites, setFavourites] = useState<Project[]>([]);
  const [error, setError] = useState('');
  const [searchFailed, setSearchFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
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
      listSeq.current += 1;
      detailsSeq.current += 1;
      setResults(null);
      setFavourites([]);
      setSelected(null);
      setDetails(null);
      setDetailsLoading(false);
      setLoading(false);
      setLoadingMore(false);
      setIdea('');
      setActiveIdea('');
      setFromCache(false);
      setError('');
      setFavouritesError('');
      void clearDiscoveryCache(previous);
    }
    // A search submitted while AsyncStorage is still resolving must win over
    // the cached page; only restore when the sequence has not moved.
    const restoreSeq = listSeq.current;
    void (async () => {
      const [cachedResults, cachedFavourites] = await Promise.all([
        loadCachedResults(account),
        loadCachedFavourites(account),
      ]);
      if (!active) return;
      if (cachedResults && listSeq.current === restoreSeq) {
        setResults(cachedResults.data);
        setFromCache(true);
      }
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

  useEffect(() => () => {
    sessionSeq.current += 1;
    listSeq.current += 1;
    detailsSeq.current += 1;
  }, []);

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

  const runSearch = async (text: string, { refresh = false } = {}) => {
    const seq = ++listSeq.current;
    const session = sessionSeq.current;
    setActiveIdea(text);
    setFromCache(false);
    setLoading(true);
    setRefreshing(refresh);
    setLoadingMore(false);
    setError('');
    setSearchFailed(false);
    if (!refresh) setResults(null);
    try {
      const data = await searchProjects(token, { idea: text, pageSize: discoveryConfig.pageSize });
      if (seq !== listSeq.current || session !== sessionSeq.current) return;
      setResults(data);
      await saveCachedResults(account, data);
    } catch (failure) {
      if (seq !== listSeq.current || session !== sessionSeq.current) return;
      const message = failureMessage(failure, 'Search failed. Please try again.');
      if (message) {
        setError(message);
        setSearchFailed(true);
      }
    } finally {
      if (seq === listSeq.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  };

  const submit = async () => {
    const text = idea.trim();
    if (text.length < discoveryConfig.minIdeaLength || text.length > discoveryConfig.maxIdeaLength) {
      setError('Describe your idea');
      setSearchFailed(false);
      return;
    }
    await runSearch(text);
  };

  // Retry and pull-to-refresh repeat the last submitted idea, not unsent edits.
  const retry = () => { if (activeIdea) void runSearch(activeIdea); };
  const refresh = () => { if (activeIdea) void runSearch(activeIdea, { refresh: true }); };

  const loadMore = async () => {
    if (!results || !activeIdea || fromCache || loading || loadingMore) return;
    const nextCursor = results.next_cursor;
    if (!nextCursor) return;
    const seq = ++listSeq.current;
    const session = sessionSeq.current;
    setLoadingMore(true);
    setError('');
    try {
      const data = await searchProjects(token, {
        idea: activeIdea,
        pageSize: discoveryConfig.pageSize,
        cursor: nextCursor,
      });
      if (seq !== listSeq.current || session !== sessionSeq.current) return;
      const items = [...results.items];
      const seen = new Set(items.map(item => item.full_name));
      for (const item of data.items) {
        if (seen.has(item.full_name)) continue;
        seen.add(item.full_name);
        items.push(item);
      }
      const combined = { ...data, items };
      setResults(combined);
      await saveCachedResults(account, combined);
    } catch (failure) {
      if (seq !== listSeq.current) return;
      // An expired or invalid cursor cannot resume: drop it, keep the idea and
      // let the user restart the search from the first page.
      if (failure instanceof DiscoveryApiError && (failure.code === 'CURSOR_EXPIRED' || failure.code === 'CURSOR_INVALID')) {
        setResults(current => current ? { ...current, next_cursor: null, has_more: false } : current);
        setError(
          failure.code === 'CURSOR_EXPIRED'
            ? 'This search expired. Search again to see more results.'
            : 'This search cannot continue. Search again to see more results.',
        );
        return;
      }
      const message = failureMessage(failure, 'Unable to load more results. Please try again.');
      if (message) setError(message);
    } finally {
      if (seq === listSeq.current) setLoadingMore(false);
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
    const session = sessionSeq.current;
    setFavouriteBusy(project.full_name);
    setFavouritesError('');
    setFavourites(next);
    try {
      if (saved) await removeFavourite(token, project.full_name);
      else await saveFavourite(token, project.full_name);
      if (session !== sessionSeq.current) return;
      await saveCachedFavourites(account, next);
    } catch (failure) {
      if (session !== sessionSeq.current) return;
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
    const seq = ++detailsSeq.current;
    setSelected(project);
    setDetails(null);
    setDetailsError('');
    setDetailsLoading(true);
    try {
      const data = await getProject(token, project.full_name);
      if (seq !== detailsSeq.current) return;
      setDetails(data);
    } catch (failure) {
      if (seq !== detailsSeq.current) return;
      const message = failureMessage(failure, 'Unable to load this project. Please try again.');
      if (message) setDetailsError(message);
    } finally {
      if (seq === detailsSeq.current) setDetailsLoading(false);
    }
  };

  const closeDetails = () => {
    detailsSeq.current += 1;
    setSelected(null);
    setDetails(null);
    setDetailsError('');
    setDetailsLoading(false);
  };

  const leave = async () => {
    sessionSeq.current += 1;
    listSeq.current += 1;
    detailsSeq.current += 1;
    await clearDiscoveryCache(account);
    onSignOut();
  };

  const canLoadMore = results !== null
    && activeIdea !== ''
    && !fromCache
    && !loading
    && results.has_more
    && results.next_cursor !== null;
  const homeResults = tab === 'Home' && !selected;
  const canRefresh = homeResults && activeIdea !== '' && !loadingMore;
  const detail = results ? sourceDetail(results) : null;
  const confirmedEmpty = results !== null && results.items.length === 0 && completeSearch(results);
  const unconfirmedEmpty = results !== null && results.items.length === 0 && !completeSearch(results);

  return <SafeAreaView style={[styles.root, { backgroundColor: colors.background }]}>
    <View style={[styles.header, { borderColor: colors.border }]}>
      <BrandMark mode={mode} size={38} />
      <View style={styles.headerText}>
        <Text accessibilityRole="header" style={[styles.title, { color: colors.text }]}>{tab === 'Home' ? 'Discover projects' : 'Profile'}</Text>
        {tab === 'Home' ? <Text style={[styles.meta, { color: colors.muted }]}>@{user.login}</Text> : null}
      </View>
    </View>
    <ScrollView
      testID="discovery-list"
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
      refreshControl={canRefresh
        ? <RefreshControl refreshing={refreshing} onRefresh={refresh} accessibilityLabel="Refresh results" />
        : undefined}
    >
      {accountError ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.error, { color: colors.text }]}>{accountError}</Text> : null}
      {favouritesError ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.error, { color: colors.text }]}>{favouritesError}</Text> : null}
      {selected ? <ProjectDetailsView
        project={selected}
        details={details}
        loading={detailsLoading}
        error={detailsError}
        saved={isSaved(selected.full_name)}
        busy={favouriteBusy === selected.full_name}
        onBack={closeDetails}
        onToggle={() => void toggleFavourite(selected)}
      /> : <>
        {tab === 'Home' ? <>
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
          {loading && !refreshing ? <BrandLoader mode={mode} label="Searching projects" /> : null}
          {error ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.error, { color: colors.text }]}>{error}</Text> : null}
          {fromCache && results ? <Text style={[styles.notice, { color: colors.muted }]}>{results.has_more
            ? 'Showing your last results. Search again to load more.'
            : 'Showing your last results. Search again for fresh results.'}</Text> : null}
          {results && results.items.length > 0 && !completeSearch(results) ? <Text accessibilityRole="alert" style={[styles.notice, { color: colors.text }]}>Some sources were unavailable. Results may be incomplete.</Text> : null}
          {unconfirmedEmpty ? <Text accessibilityRole="alert" style={[styles.notice, { color: colors.text }]}>No results could be confirmed because a source was unavailable.</Text> : null}
          {detail ? <Text style={[styles.notice, { color: colors.muted }]}>{detail}</Text> : null}
          {confirmedEmpty ? <Text style={[styles.notice, { color: colors.muted }]}>No projects matched your idea. Try different keywords.</Text> : null}
          {(searchFailed || (unconfirmedEmpty && !fromCache)) && activeIdea && !loading ? <Pressable
            accessibilityRole="button"
            accessibilityLabel="Try again"
            onPress={retry}
            style={[styles.more, { borderColor: colors.border }]}
          >
            <Text style={{ color: colors.text }}>Try again</Text>
          </Pressable> : null}
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
          {user.avatar_url ? <Image source={{ uri: user.avatar_url }} accessibilityLabel={`GitHub avatar for ${user.login}`} style={{ width: 64, height: 64, borderRadius: 32 }} /> : null}
          <Text accessibilityRole="header" style={[styles.title, { color: colors.text }]}>@{user.login}</Text>
          <Text accessibilityRole="header" style={[styles.sectionHeading, { color: colors.text }]}>Favourites</Text>
          {favourites.length === 0 ? <Text style={[styles.notice, { color: colors.muted }]}>No favourites yet.</Text> : null}
          {favourites.map(project => <ProjectCard
            key={project.full_name}
            project={project}
            saved
            busy={favouriteBusy === project.full_name}
            onOpen={() => void openDetails(project)}
            onToggle={() => void toggleFavourite(project)}
          />)}
          <Text accessibilityRole="header" style={[styles.sectionHeading, { color: colors.text }]}>Settings</Text>
          <Text style={[styles.settingLabel, { color: colors.muted }]}>Appearance</Text>
          <AppearanceControls />
          <Text accessibilityRole="header" style={[styles.sectionHeading, { color: colors.text }]}>About and privacy</Text>
          <Text style={[styles.notice, { color: colors.muted }]}>Your device stores your sign-in session, appearance preference and account-specific cached results and favourites. Signing out clears your account cache. Your idea goes to the backend to search GitHub and the project archive; it is not saved in the results cache. Favourites are saved to your backend account.</Text>
          <Pressable accessibilityRole="button" accessibilityState={{ disabled: signingOut }} disabled={signingOut} onPress={() => void leave()} style={[styles.more, { borderColor: colors.border }]}>
            <Text style={{ color: colors.text }}>{signingOut ? 'Signing out' : 'Sign out'}</Text>
          </Pressable>
        </>}
      </>}
    </ScrollView>
    <View style={[styles.tabs, { padding: 20, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border }]}>
      {(['Home', 'Profile'] as const).map(name => <Pressable key={name} accessibilityRole="tab" accessibilityLabel={name} accessibilityState={{ selected: tab === name }} onPress={() => { closeDetails(); setTab(name); }} style={[styles.tab, { minHeight: 48, backgroundColor: tab === name ? colors.accent : colors.surface, borderColor: colors.border }]}>
        <Text style={{ color: tab === name ? colors.onAccent : colors.text }}>{name}</Text>
      </Pressable>)}
    </View>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  headerText: { flex: 1 },
  title: { fontSize: 22, lineHeight: 28, fontWeight: '700' },
  sectionHeading: { fontSize: 17, lineHeight: 24, fontWeight: '600', marginTop: 8 },
  settingLabel: { fontSize: 14, lineHeight: 20, fontWeight: '500', paddingLeft: 8 },
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
