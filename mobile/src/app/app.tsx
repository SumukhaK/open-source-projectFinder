import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SystemUI from 'expo-system-ui';
import { getThemeColors } from '../config/branding';
import { BrandLoader } from '../components/brand-loader';
import { AuthScreen, AuthSessionView } from '../features/auth/components/auth-screen';
import { DiscoveryScreen } from '../features/discovery/components/discovery-screen';
import { useTheme } from '../lib/theme';
import { CrashBoundary } from '../components/crash-boundary';
import { AppProvider } from './provider';

function DiscoverySession({ token, user, signOut, signingOut, accountError, onUnauthorized }: AuthSessionView) {
  return <DiscoveryScreen
    token={token}
    user={user}
    onSignOut={signOut}
    signingOut={signingOut}
    accountError={accountError}
    onUnauthorized={onUnauthorized}
  />;
}

function AppContent() {
  const { mode, ready } = useTheme();
  const backgroundColor = getThemeColors(mode).background;
  useEffect(() => { void SystemUI.setBackgroundColorAsync(backgroundColor); }, [backgroundColor]);
  return <View style={[styles.root, { backgroundColor }]}>
    <StatusBar style={mode === 'dark' ? 'light' : 'dark'} />
    {ready ? <AuthScreen renderSignedIn={DiscoverySession} /> : <View style={styles.startup}><BrandLoader mode={mode} label="Opening RepoRadar" /></View>}
  </View>;
}
export default function App() { return <CrashBoundary><AppProvider><AppContent /></AppProvider></CrashBoundary>; }
const styles = StyleSheet.create({ root: { flex: 1 }, startup: { flex: 1, alignItems: 'center', justifyContent: 'center' } });
