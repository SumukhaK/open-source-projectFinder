import React from 'react';
import { Pressable, StyleSheet, Text, useColorScheme, View } from 'react-native';
import { BrandMark } from './brand-mark';
import { getThemeColors } from '../config/branding';

type CrashEvent = { event: 'mobile_render_crash' };
const reportCrash = (event: CrashEvent) => console.error(JSON.stringify(event));
function Recovery({ retry }: { retry: () => void }) {
  const mode = useColorScheme() === 'light' ? 'light' : 'dark';
  const colors = getThemeColors(mode);
  return <View style={[styles.container, { backgroundColor: colors.background }]}>
    <BrandMark mode={mode} size={80} />
    <Text accessibilityRole="header" style={[styles.title, { color: colors.text }]}>Something went wrong</Text>
    <Text style={[styles.description, { color: colors.muted }]}>Please try opening this screen again.</Text>
    <Pressable accessibilityRole="button" onPress={retry} style={[styles.button, { backgroundColor: colors.accent }]}>
      <Text style={{ color: colors.onAccent, fontWeight: '600' }}>Try again</Text>
    </Pressable>
  </View>;
}
export class CrashBoundary extends React.Component<{ children: React.ReactNode; report?: (event: CrashEvent) => void }, { failed: boolean; attempt: number }> {
  state = { failed: false, attempt: 0 };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { (this.props.report ?? reportCrash)({ event: 'mobile_render_crash' }); }
  render() {
    return this.state.failed ? <Recovery retry={() => this.setState(state => ({ failed: false, attempt: state.attempt + 1 }))} /> : <React.Fragment key={this.state.attempt}>{this.props.children}</React.Fragment>;
  }
}
const styles = StyleSheet.create({ container: { flex: 1, padding: 28, gap: 22, alignItems: 'center', justifyContent: 'center' }, title: { fontSize: 24, fontWeight: '700', textAlign: 'center' }, description: { fontSize: 16, textAlign: 'center' }, button: { minHeight: 48, padding: 16, borderRadius: 12, justifyContent: 'center' } });
