import * as WebBrowser from 'expo-web-browser';
import { signIn, getUser, logout } from '../src/features/auth/api/auth';
jest.mock('expo-web-browser', () => ({ openAuthSessionAsync: jest.fn(), WebBrowserResultType: { CANCEL: 'cancel' } }));
jest.mock('expo-crypto', () => ({ getRandomBytesAsync: jest.fn(async () => new Uint8Array(32).fill(1)), digestStringAsync: jest.fn(async () => 'challenge'), CryptoDigestAlgorithm: { SHA256: 'SHA-256' }, CryptoEncoding: { BASE64: 'base64' } }));
beforeEach(() => { jest.clearAllMocks(); });
test('checks callback state before exchanging handoff', async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ authorization_url: 'https://github.com/login/oauth/authorize', state: 'expected' }) });
  jest.mocked(WebBrowser.openAuthSessionAsync).mockResolvedValue({ type: 'success', url: 'reporadar://auth/callback?state=wrong&code=handoff' });
  await expect(signIn()).rejects.toThrow('Invalid sign-in response');
  expect(fetch).toHaveBeenCalledTimes(1);
});
test('successful browser handoff exchanges proof and returns only app session', async () => {
  const session = { token: 'app-session', user: { github_id: 1, login: 'test', avatar_url: '' }, expires_at: 123 };
  global.fetch = jest.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ authorization_url: 'https://github.com/login/oauth/authorize', state: 'expected' }) }).mockResolvedValueOnce({ ok: true, json: async () => session });
  jest.mocked(WebBrowser.openAuthSessionAsync).mockResolvedValue({ type: 'success', url: 'reporadar://auth/callback?state=expected&code=handoff' });
  expect(await signIn()).toEqual(session);
  expect(JSON.parse((jest.mocked(fetch).mock.calls[1][1] as RequestInit).body as string)).toMatchObject({ code: 'handoff' });
});
test('browser cancellation does not exchange a token', async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ authorization_url: 'https://github.com/login/oauth/authorize', state: 'expected' }) });
  jest.mocked(WebBrowser.openAuthSessionAsync).mockResolvedValue({ type: WebBrowser.WebBrowserResultType.CANCEL });
  await expect(signIn()).rejects.toThrow('Sign-in cancelled');
  expect(fetch).toHaveBeenCalledTimes(1);
});

test.each([401, 429, 503, 500])('HTTP %s produces a safe error without leaking response content', async status => {
  global.fetch = jest.fn().mockResolvedValue({ ok: false, status, headers: { get: () => '60' }, json: async () => ({ detail: 'private provider data' }) });
  await expect(getUser('session')).rejects.toThrow(status === 401 ? 'session expired' : status === 429 ? 'Too many requests' : status === 503 ? 'not available yet' : 'Sign-in failed');
});
test('network failure is safe and logout accepts an empty 204 response', async () => {
  global.fetch = jest.fn().mockRejectedValue(new Error('private transport details'));
  await expect(getUser('session')).rejects.toThrow('Unable to connect');
  global.fetch = jest.fn().mockResolvedValue({ ok: true, status: 204 });
  await expect(logout('session')).resolves.toBeUndefined();
});
