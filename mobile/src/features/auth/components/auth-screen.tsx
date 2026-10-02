import React, { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BrandLoader } from '../../../components/brand-loader';
import { AppearanceControls } from '../../../components/appearance-controls';
import { BrandMark } from '../../../components/brand-mark';
import { branding } from '../../../config/branding';
import { useTheme } from '../../../lib/theme';
import { ApiError, getUser, logout, signIn, User } from '../api/auth';
import { clearToken, readToken, saveToken } from '../session-storage';

export function AuthScreen({ children }: { children?: React.ReactNode }) {
  const { mode } = useTheme();
  const colors = branding.themes[mode];
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const active = useRef(false);
  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const saved = await readToken();
        if (saved) {
          try {
            const restored = await getUser(saved);
            if (mounted) { setUser(restored); setToken(saved); }
          } catch (failure) {
            if (failure instanceof ApiError && failure.status === 401) await clearToken();
            else throw failure;
          }
        }
      } catch { if (mounted) setError('Unable to restore your session. Please try signing in again.'); }
      finally { if (mounted) setReady(true); }
    })();
    return () => { mounted = false; };
  }, []);
  const authenticate = async () => {
    if (active.current) return;
    active.current = true; setBusy(true); setError('');
    try {
      if (token) {
        try { await logout(token); } catch (failure) { if (!(failure instanceof ApiError && failure.status === 401)) throw failure; }
        await clearToken(); setToken(null); setUser(null);
      } else {
        const session = await signIn();
        try { await saveToken(session.token); }
        catch { await logout(session.token).catch(() => undefined); throw new Error('Unable to save your session securely. Please try again.'); }
        setToken(session.token); setUser(session.user);
      }
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Sign-in failed. Try again.'); }
    finally { active.current = false; setBusy(false); }
  };
  if (!ready) return <View style={styles.loading}><BrandLoader mode={mode} label="Restoring your session" /></View>;
  return <SafeAreaView style={[styles.root, { backgroundColor: colors.background }]}>
    <ScrollView contentContainerStyle={styles.content}>
      <BrandMark mode={mode} size={112} />
      <Text style={[styles.wordmark, { color: colors.text }]}>RepoRadar</Text>
      <Text accessibilityRole="header" style={[styles.title, { color: colors.text }]}>{user ? `Signed in as @${user.login}` : 'Your next idea starts here.'}</Text>
      <Text style={[styles.description, { color: colors.muted }]}>{user ? 'Your account is ready. Project discovery is coming next.' : 'Continue with your GitHub account to discover where your idea already lives.'}</Text>
      {busy && <BrandLoader mode={mode} label={token ? 'Signing out' : 'Signing in with GitHub'} />}
      {error ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.description, { color: colors.text }]}>{error}</Text> : null}
      <Pressable accessibilityRole="button" accessibilityState={{ disabled: busy }} disabled={busy} onPress={() => void authenticate()} style={[styles.button, { backgroundColor: colors.accent, opacity: busy ? 0.6 : 1 }]}>
        <Text style={[styles.buttonText, { color: colors.onAccent }]}>{user ? 'Sign out' : 'Continue with GitHub'}</Text>
      </Pressable>
      <AppearanceControls />
      {!user && <Text style={[styles.caption, { color: colors.muted }]}>One account for signup and login. No private repository access requested.</Text>}
    </ScrollView>
    {user && children}
  </SafeAreaView>;
}
const styles = StyleSheet.create({
  root: { flex: 1 }, loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  content: { flexGrow: 1, alignItems: 'center', justifyContent: 'center', padding: 28, gap: 22, width: '100%', maxWidth: 560, alignSelf: 'center' },
  wordmark: { fontSize: 26, fontWeight: '700' }, title: { fontSize: 30, lineHeight: 38, fontWeight: '700', textAlign: 'center' },
  description: { fontSize: 16, lineHeight: 25, textAlign: 'center' }, caption: { fontSize: 13, lineHeight: 20, textAlign: 'center' },
  button: { minHeight: 52, paddingHorizontal: 24, borderRadius: 14, alignItems: 'center', justifyContent: 'center', width: '100%' },
  buttonText: { fontSize: 16, fontWeight: '600' },
});
