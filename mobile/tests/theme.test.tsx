import React from 'react';
import { Text, Pressable } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { ThemeProvider, useTheme } from '../src/lib/theme';
import { resolveTheme } from '../src/lib/resolve-theme';

function Probe() {
  const { mode, preference, setPreference, ready } = useTheme();
  return <><Text>{ready ? `${preference}:${mode}` : 'starting'}</Text>
    <Pressable accessibilityRole="button" onPress={() => setPreference('dark')}><Text>Dark</Text></Pressable>
    <Pressable accessibilityRole="button" onPress={() => setPreference('system')}><Text>System</Text></Pressable></>;
}

beforeEach(async () => { jest.clearAllMocks(); await AsyncStorage.clear(); });

test('system appearance follows the OS and falls back to dark when unavailable', () => {
  expect(resolveTheme('system', 'light')).toBe('light');
  expect(resolveTheme('system', 'dark')).toBe('dark');
  expect(resolveTheme('system', null)).toBe('dark');
  expect(resolveTheme('light', 'dark')).toBe('light');
  expect(resolveTheme('dark', 'light')).toBe('dark');
});

test('restores saved appearance and persists user changes', async () => {
  await AsyncStorage.setItem('reporadar.appearance', 'light');
  const screen = await render(<ThemeProvider><Probe /></ThemeProvider>);
  await waitFor(() => expect(screen.getByText('light:light')).toBeTruthy());
  await fireEvent.press(screen.getByText('Dark'));
  await waitFor(() => expect(screen.getByText('dark:dark')).toBeTruthy());
  expect(await AsyncStorage.getItem('reporadar.appearance')).toBe('dark');
  await fireEvent.press(screen.getByText('System'));
  await waitFor(() => expect(AsyncStorage.setItem).toHaveBeenLastCalledWith('reporadar.appearance', 'system'));
});

test('invalid saved preferences fall back to system', async () => {
  await AsyncStorage.setItem('reporadar.appearance', 'invalid');
  const screen = await render(<ThemeProvider><Probe /></ThemeProvider>);
  await waitFor(() => expect(screen.queryByText('starting')).toBeNull());
  expect(screen.getByText(/^system:/)).toBeTruthy();
});

test('storage failure still allows startup', async () => {
  jest.spyOn(AsyncStorage, 'getItem').mockRejectedValueOnce(new Error('unavailable'));
  const screen = await render(<ThemeProvider><Probe /></ThemeProvider>);
  await waitFor(() => expect(screen.getByText(/^system:/)).toBeTruthy());
});
