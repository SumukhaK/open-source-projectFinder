import React from 'react';
import { AccessibilityInfo } from 'react-native';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { BrandingScreen } from '../src/features/branding/components/branding-screen';
import { AppProvider } from '../src/app/provider';

beforeEach(async () => {
  await AsyncStorage.clear();
  jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);
});

test('appearance controls update selection and the loading preview can be stopped', async () => {
  const screen = await render(<AppProvider><BrandingScreen /></AppProvider>);
  await waitFor(() => expect(screen.getByRole('radio', { name: 'System appearance' }).props.accessibilityState.checked).toBe(true));
  await fireEvent.press(screen.getByRole('radio', { name: 'Light appearance' }));
  expect(screen.getByRole('radio', { name: 'Light appearance' }).props.accessibilityState.checked).toBe(true);
  await fireEvent.press(screen.getByRole('button', { name: 'Preview loading animation' }));
  expect(screen.getByRole('progressbar', { name: 'Loading preview' })).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Stop animation preview' }));
  expect(screen.queryByRole('progressbar')).toBeNull();
});
