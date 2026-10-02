import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SystemUI from 'expo-system-ui';
import { branding } from '../config/branding';
import { BrandLoader } from '../components/brand-loader';
import { AuthScreen } from '../features/auth/components/auth-screen';
import { useTheme } from '../lib/theme';
import { AppProvider } from './provider';

function AppContent() {
  const { mode, ready } = useTheme();
  const backgroundColor = branding.themes[mode].background;
  useEffect(() => { void SystemUI.setBackgroundColorAsync(backgroundColor); }, [backgroundColor]);
  return <View style={[styles.root, { backgroundColor }]}>
    <StatusBar style={mode === 'dark' ? 'light' : 'dark'} />
    {ready ? <AuthScreen /> : <View style={styles.startup}><BrandLoader mode={mode} label="Opening RepoRadar" /></View>}
  </View>;
}
export default function App() { return <AppProvider><AppContent /></AppProvider>; }
const styles = StyleSheet.create({ root: { flex: 1 }, startup: { flex: 1, alignItems: 'center', justifyContent: 'center' } });
