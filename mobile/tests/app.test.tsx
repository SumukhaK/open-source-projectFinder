import React from 'react';
import { AccessibilityInfo } from 'react-native';
import { render, waitFor } from '@testing-library/react-native';
import App from '../src/app/app';
jest.mock('expo-system-ui', () => ({ setBackgroundColorAsync: jest.fn(async () => undefined) }));
jest.mock('../src/features/auth/session-storage', () => ({ readToken: jest.fn(async () => null) }));
test('app startup routes an unauthenticated user to GitHub sign-in', async () => {
  jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);
  const screen = await render(<App />);
  await waitFor(() => expect(screen.getByText('Continue with GitHub')).toBeTruthy());
});
