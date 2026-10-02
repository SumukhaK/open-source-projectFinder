import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { AccessibilityInfo } from 'react-native';
import { AuthScreen } from '../src/features/auth/components/auth-screen';
import { AppProvider } from '../src/app/provider';
import * as auth from '../src/features/auth/api/auth';
import * as storage from '../src/features/auth/session-storage';

jest.mock('../src/features/auth/api/auth', () => ({ signIn: jest.fn(), getUser: jest.fn(), logout: jest.fn(), ApiError: class ApiError extends Error { status: number; constructor(message: string, status: number) { super(message); this.status = status; } } }));
jest.mock('../src/features/auth/session-storage', () => ({ readToken: jest.fn(), saveToken: jest.fn(), clearToken: jest.fn() }));
const user = { github_id: 123, login: 'octocat', avatar_url: '' };
beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);
  jest.mocked(storage.readToken).mockResolvedValue(null);
  jest.mocked(storage.saveToken).mockResolvedValue(undefined);
  jest.mocked(storage.clearToken).mockResolvedValue(undefined);
});
test('single GitHub action signs up, shows account and logs out', async () => {
  jest.mocked(auth.signIn).mockResolvedValue({ token: 'session', expires_at: 9999999999, user });
  jest.mocked(auth.logout).mockResolvedValue(undefined);
  const screen = await render(<AppProvider><AuthScreen /></AppProvider>);
  await waitFor(() => expect(screen.getByText('Continue with GitHub')).toBeTruthy());
  await fireEvent.press(screen.getByText('Continue with GitHub'));
  await waitFor(() => expect(screen.getByText('Signed in as @octocat')).toBeTruthy());
  expect(storage.saveToken).toHaveBeenCalledWith('session');
  await fireEvent.press(screen.getByText('Sign out'));
  await waitFor(() => expect(screen.getByText('Continue with GitHub')).toBeTruthy());
  expect(auth.logout).toHaveBeenCalledWith('session');
});
test('valid saved session skips login and expired session clears storage', async () => {
  jest.mocked(storage.readToken).mockResolvedValue('saved');
  jest.mocked(auth.getUser).mockResolvedValue(user);
  const screen = await render(<AppProvider><AuthScreen /></AppProvider>);
  await waitFor(() => expect(screen.getByText('Signed in as @octocat')).toBeTruthy());
  await screen.unmount();
  jest.mocked(auth.getUser).mockRejectedValue(new auth.ApiError('expired', 401));
  const expired = await render(<AppProvider><AuthScreen /></AppProvider>);
  await waitFor(() => expect(expired.getByText('Continue with GitHub')).toBeTruthy());
  expect(storage.clearToken).toHaveBeenCalled();
});

test('pending login disables repeated clicks and failures allow retry', async () => {
  let reject!: (error: Error) => void;
  jest.mocked(auth.signIn).mockReturnValue(new Promise((_, fail) => { reject = fail; }));
  const screen = await render(<AppProvider><AuthScreen /></AppProvider>);
  await waitFor(() => expect(screen.getByText('Continue with GitHub')).toBeTruthy());
  await fireEvent.press(screen.getByText('Continue with GitHub'));
  expect(screen.getByRole('progressbar', { name: 'Signing in with GitHub' })).toBeTruthy();
  await fireEvent.press(screen.getByText('Continue with GitHub'));
  expect(auth.signIn).toHaveBeenCalledTimes(1);
  reject(new Error('GitHub is temporarily unavailable. Try again.'));
  await waitFor(() => expect(screen.getByText('GitHub is temporarily unavailable. Try again.')).toBeTruthy());
});

test('transient restore failure preserves the saved token', async () => {
  jest.mocked(storage.readToken).mockResolvedValue('saved');
  jest.mocked(auth.getUser).mockRejectedValue(new Error('offline'));
  const screen = await render(<AppProvider><AuthScreen /></AppProvider>);
  await waitFor(() => expect(screen.getByText('Unable to restore your session. Please try signing in again.')).toBeTruthy());
  expect(storage.clearToken).not.toHaveBeenCalled();
});
test('failed logout keeps the account until server revocation can be retried', async () => {
  jest.mocked(storage.readToken).mockResolvedValue('saved');
  jest.mocked(auth.getUser).mockResolvedValue(user);
  jest.mocked(auth.logout).mockRejectedValue(new Error('offline'));
  const screen = await render(<AppProvider><AuthScreen /></AppProvider>);
  await waitFor(() => expect(screen.getByText('Signed in as @octocat')).toBeTruthy());
  await fireEvent.press(screen.getByText('Sign out'));
  await waitFor(() => expect(screen.getByText('offline')).toBeTruthy());
  expect(storage.clearToken).not.toHaveBeenCalled();
  expect(screen.getByText('Signed in as @octocat')).toBeTruthy();
});
test('secure storage failure revokes the new server session', async () => {
  jest.mocked(auth.signIn).mockResolvedValue({ token: 'new', expires_at: 9999999999, user });
  jest.mocked(storage.saveToken).mockRejectedValue(new Error('storage failed'));
  jest.mocked(auth.logout).mockResolvedValue(undefined);
  const screen = await render(<AppProvider><AuthScreen /></AppProvider>);
  await waitFor(() => expect(screen.getByText('Continue with GitHub')).toBeTruthy());
  await fireEvent.press(screen.getByText('Continue with GitHub'));
  await waitFor(() => expect(screen.getByText('Unable to save your session securely. Please try again.')).toBeTruthy());
  expect(auth.logout).toHaveBeenCalledWith('new');
  expect(screen.queryByText('Signed in as @octocat')).toBeNull();
});
