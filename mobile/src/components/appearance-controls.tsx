import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { branding, ThemePreference } from '../config/branding';
import { useTheme } from '../lib/theme';

export function AppearanceControls() {
  const { mode, preference, setPreference } = useTheme();
  const colors = branding.themes[mode];
  const options: ThemePreference[] = ['system', 'dark', 'light'];
  return <View style={styles.options}>
    {options.map(option => <Pressable key={option} accessibilityRole="radio"
      accessibilityLabel={`${option.charAt(0).toUpperCase() + option.slice(1)} appearance`}
      accessibilityState={{ checked: preference === option }} aria-checked={preference === option}
      onPress={() => setPreference(option)}
      style={[styles.option, { backgroundColor: preference === option ? colors.accent : colors.surface }]}>
      <Text style={{ color: preference === option ? colors.onAccent : colors.text, fontWeight: '600' }}>
        {option.charAt(0).toUpperCase() + option.slice(1)}</Text>
    </Pressable>)}
  </View>;
}
const styles = StyleSheet.create({ options: { flexDirection: 'row', gap: 8, width: '100%' }, option: { flex: 1, minHeight: 48, padding: 8, borderRadius: 12, justifyContent: 'center', alignItems: 'center' } });
