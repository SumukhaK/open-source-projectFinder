import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ThemeProvider } from '../lib/theme';

export function AppProvider({ children }: { children: React.ReactNode }) {
  return <SafeAreaProvider><ThemeProvider>{children}</ThemeProvider></SafeAreaProvider>;
}
