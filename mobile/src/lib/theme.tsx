import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { useColorScheme } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { branding, ThemeMode, ThemePreference } from '../config/branding';
import { resolveTheme } from './resolve-theme';

type ThemeContextValue = {
  mode: ThemeMode;
  preference: ThemePreference;
  ready: boolean;
  setPreference: (preference: ThemePreference) => void;
};
const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const system = useColorScheme();
  const [preference, setValue] = useState<ThemePreference>('system');
  const [ready, setReady] = useState(false);
  const writes = useRef(Promise.resolve());

  useEffect(() => {
    let active = true;
    async function restore() {
      try {
        const saved = await AsyncStorage.getItem(branding.appearanceStorageKey);
        if (active && (saved === 'system' || saved === 'dark' || saved === 'light')) setValue(saved);
      } catch {
        // A storage failure must not prevent startup; use the system preference.
      } finally {
        if (active) setReady(true);
      }
    }
    void restore();
    return () => { active = false; };
  }, []);

  function setPreference(next: ThemePreference) {
    setValue(next);
    // Serialize writes so rapid theme changes preserve the latest selection.
    writes.current = writes.current.then(() => AsyncStorage.setItem(branding.appearanceStorageKey, next)).catch(() => {
      // The selected theme remains usable in this session if persistence fails.
    });
  }

  return <ThemeContext.Provider value={{ mode: resolveTheme(preference, system), preference, ready, setPreference }}>
    {children}
  </ThemeContext.Provider>;
}

export function useTheme() {
  const theme = useContext(ThemeContext);
  if (!theme) throw new Error('useTheme requires ThemeProvider');
  return theme;
}
