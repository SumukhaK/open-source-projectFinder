import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { BrandLoader } from '../../../components/brand-loader';
import { getThemeColors } from '../../../config/branding';
import { useTheme } from '../../../lib/theme';
import { Project, ProjectDetails } from '../api/discovery';

export function ProjectDetailsView({ project, details, loading, error, saved, busy, onBack, onToggle }: {
  project: Project;
  details: ProjectDetails | null;
  loading: boolean;
  error: string;
  saved: boolean;
  busy: boolean;
  onBack: () => void;
  onToggle: () => void;
}) {
  const { mode } = useTheme();
  const colors = getThemeColors(mode);
  const shown = details ?? project;
  return <View style={styles.root}>
    <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={onBack} style={styles.back}>
      <Text style={[styles.link, { color: colors.accent }]}>Back to results</Text>
    </Pressable>
    <Text accessibilityRole="header" style={[styles.title, { color: colors.text }]}>{project.name}</Text>
    <Text style={[styles.meta, { color: colors.muted }]}>{project.full_name}</Text>
    {shown.description ? <Text style={[styles.body, { color: colors.text }]}>{shown.description}</Text> : null}
    <View style={styles.stats}>
      <Text style={[styles.meta, { color: colors.muted }]}>{shown.stars} stars</Text>
      <Text style={[styles.meta, { color: colors.muted }]}>{shown.language ?? 'Language not reported'}</Text>
      <Text style={[styles.meta, { color: colors.muted }]}>{shown.license ? `Licence ${shown.license}` : 'Licence not reported'}</Text>
    </View>
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked: saved, disabled: busy }}
      accessibilityLabel={`${saved ? 'Remove' : 'Save'} ${project.full_name} ${saved ? 'from' : 'to'} favourites`}
      disabled={busy}
      onPress={onToggle}
      style={[styles.favourite, { borderColor: colors.border }]}
    >
      <Text style={{ color: saved ? colors.accent : colors.text }}>{saved ? '★ Remove from favourites' : '☆ Save to favourites'}</Text>
    </Pressable>
    {loading ? <BrandLoader mode={mode} label="Loading project details" /> : null}
    {error ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.error, { color: colors.text }]}>{error}</Text> : null}
    {details ? <View style={styles.sections}>
      {Object.keys(details.languages).length > 0 ? <View style={styles.section}>
        <Text accessibilityRole="header" style={[styles.heading, { color: colors.text }]}>Languages</Text>
        {Object.entries(details.languages).map(([name, bytes]) => <Text key={name} style={[styles.meta, { color: colors.muted }]}>{name} · {bytes}</Text>)}
      </View> : null}
      {details.releases.length > 0 ? <View style={styles.section}>
        <Text accessibilityRole="header" style={[styles.heading, { color: colors.text }]}>Releases</Text>
        {details.releases.map(release => <Text key={release.tag} style={[styles.meta, { color: colors.muted }]}>{release.name}</Text>)}
      </View> : null}
      {details.readme ? <View style={styles.section}>
        <Text accessibilityRole="header" style={[styles.heading, { color: colors.text }]}>README</Text>
        <Text style={[styles.body, { color: colors.muted }]}>{details.readme}</Text>
        {details.readme_truncated ? <Text style={[styles.meta, { color: colors.muted }]}>README truncated.</Text> : null}
      </View> : null}
      {details.contributors.length > 0 ? <View style={styles.section}>
        <Text accessibilityRole="header" style={[styles.heading, { color: colors.text }]}>Contributors</Text>
        {details.contributors.map(contributor => <Text key={contributor.login} style={[styles.meta, { color: colors.muted }]}>{contributor.login}</Text>)}
      </View> : null}
    </View> : null}
  </View>;
}

const styles = StyleSheet.create({
  root: { gap: 10 },
  back: { minHeight: 44, justifyContent: 'center' },
  link: { fontSize: 15, fontWeight: '600' },
  title: { fontSize: 26, lineHeight: 34, fontWeight: '700' },
  body: { fontSize: 15, lineHeight: 23 },
  meta: { fontSize: 13, lineHeight: 20 },
  stats: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  favourite: { minHeight: 48, borderWidth: 1, borderRadius: 12, paddingHorizontal: 14, justifyContent: 'center' },
  error: { fontSize: 15, lineHeight: 23 },
  sections: { gap: 18, marginTop: 8 },
  section: { gap: 6 },
  heading: { fontSize: 18, lineHeight: 24, fontWeight: '600' },
});
