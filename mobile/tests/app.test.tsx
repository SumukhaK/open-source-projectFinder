import React from 'react';
import { AccessibilityInfo } from 'react-native';
import { render, waitFor } from '@testing-library/react-native';
import App from '../src/app/app';
import * as auth from '../src/features/auth/api/auth';
import * as storage from '../src/features/auth/session-storage';
import * as discovery from '../src/features/discovery/api/discovery';

jest.mock('expo-system-ui', () => ({ setBackgroundColorAsync: jest.fn(async () => undefined) }));
jest.mock('../src/features/auth/session-storage', () => ({
  readToken: jest.fn(async () => null),
  saveToken: jest.fn(async () => undefined),
  clearToken: jest.fn(async () => undefined),
}));
jest.mock('../src/features/discovery/api/discovery', () => ({
  ...jest.requireActual('../src/features/discovery/api/discovery'),
  getFavourites: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);
  jest.mocked(storage.readToken).mockResolvedValue(null);
  jest.mocked(discovery.getFavourites).mockResolvedValue({ items: [] });
});

test('app startup routes an unauthenticated user to GitHub sign-in', async () => {
  const screen = await render(<App />);
  await waitFor(() => expect(screen.getByText('Continue with GitHub')).toBeTruthy());
});

test('a restored session composes discovery behind sign-in', async () => {
  jest.mocked(storage.readToken).mockResolvedValue('saved');
  jest.spyOn(auth, 'getUser').mockResolvedValue({ github_id: 123, login: 'octocat', avatar_url: '' });
  const screen = await render(<App />);
  await waitFor(() => expect(screen.getByText('Discover projects')).toBeTruthy());
  expect(discovery.getFavourites).toHaveBeenCalledWith('saved');
});
