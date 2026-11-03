import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { getThemeColors } from '../../../config/branding';
import { useTheme } from '../../../lib/theme';
import { Project } from '../api/discovery';

export function ProjectCard({ project, saved, busy, onOpen, onToggle }: {
  project: Project;
  saved: boolean;
  busy: boolean;
  onOpen: () => void;
  onToggle: () => void;
}) {
  const { mode } = useTheme();
  const colors = getThemeColors(mode);
  return <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
    <View style={styles.row}>
      <Pressable accessibilityRole="button" accessibilityLabel={`Open ${project.full_name}`} onPress={onOpen} style={styles.open}>
        <Text style={[styles.owner, { color: colors.muted }]}>{project.owner}</Text>
        <Text numberOfLines={2} style={[styles.name, { color: colors.text }]}>{project.name}</Text>
      </Pressable>
      <Pressable
        accessibilityRole="checkbox"
        accessibilityState={{ checked: saved, disabled: busy }}
        accessibilityLabel={`${saved ? 'Remove' : 'Save'} ${project.full_name} ${saved ? 'from' : 'to'} favourites`}
        disabled={busy}
        onPress={onToggle}
        style={styles.toggle}
      >
        <Text style={[styles.toggleText, { color: saved ? colors.accent : colors.muted }]}>{saved ? '★' : '☆'}</Text>
      </Pressable>
    </View>
    {project.description ? <Text numberOfLines={3} style={[styles.description, { color: colors.muted }]}>{project.description}</Text> : null}
    <View style={styles.stats}>
      <Text style={[styles.meta, { color: colors.muted }]}>{project.stars} stars</Text>
      <Text style={[styles.meta, { color: colors.muted }]}>{project.language ?? 'Language not reported'}</Text>
      <Text style={[styles.meta, { color: colors.muted }]}>{project.license ? `Licence ${project.license}` : 'Licence not reported'}</Text>
    </View>
  </View>;
}

const styles = StyleSheet.create({
  card: { padding: 16, borderRadius: 16, borderWidth: 1, gap: 10, marginBottom: 12 },
  row: { flexDirection: 'row', alignItems: 'center' },
  open: { flex: 1, minHeight: 48, justifyContent: 'center' },
  owner: { fontSize: 13, lineHeight: 20 },
  name: { fontSize: 19, lineHeight: 26, fontWeight: '600' },
  toggle: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center' },
  toggleText: { fontSize: 24, lineHeight: 30 },
  description: { fontSize: 15, lineHeight: 23 },
  stats: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  meta: { fontSize: 13, lineHeight: 20 },
});
