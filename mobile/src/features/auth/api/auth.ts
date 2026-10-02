import { Platform } from 'react-native';
import * as Crypto from 'expo-crypto';
import * as WebBrowser from 'expo-web-browser';
import { authConfig } from '../../../config/auth';

export type User = { github_id: number; login: string; avatar_url: string };
export type Session = { token: string; expires_at: number; user: User };
export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const base = new URL(authConfig.apiUrl);
  if (base.protocol !== 'https:' && !__DEV__) throw new Error('Sign-in requires a secure backend connection.');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), authConfig.timeoutMs);
  try {
    const response = await fetch(authConfig.apiUrl.replace(/\/$/, '') + path, { ...init, signal: controller.signal, headers: { 'Content-Type': 'application/json', ...init.headers } });
    if (!response.ok) {
      const message = response.status === 429 ? `Too many requests. Try again in ${response.headers.get('Retry-After') ?? '60'} seconds.` : response.status === 401 ? 'Your session expired. Sign in again.' : response.status === 503 ? 'GitHub sign-in is not available yet. Try again later.' : 'Sign-in failed. Please try again.';
      throw new ApiError(message, response.status);
    }
    return response.status === 204 ? undefined as T : await response.json() as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new Error('Unable to connect. Check your connection and try again.');
  } finally { clearTimeout(timeout); }
}
export async function signIn(): Promise<Session> {
  if (Platform.OS === 'web') throw new Error('GitHub sign-in is available in the iOS and Android development builds.');
  const bytes = await Crypto.getRandomBytesAsync(32);
  const verifier = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  const challenge = (await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, verifier, { encoding: Crypto.CryptoEncoding.BASE64 })).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const start = await request<{ authorization_url: string; state: string }>('/auth/github/start', { method: 'POST', body: JSON.stringify({ challenge, redirect_uri: authConfig.redirectUri }) });
  const authorization = new URL(start.authorization_url);
  if (authorization.origin !== 'https://github.com' || authorization.pathname !== '/login/oauth/authorize') throw new Error('Invalid sign-in response');
  const result = await WebBrowser.openAuthSessionAsync(start.authorization_url, authConfig.redirectUri);
  if (result.type !== 'success') throw new Error('Sign-in cancelled. You can try again.');
  const callback = new URL(result.url);
  if (callback.protocol !== 'reporadar:' || callback.host !== 'auth' || callback.pathname !== '/callback' || callback.searchParams.get('state') !== start.state) throw new Error('Invalid sign-in response');
  if (callback.searchParams.has('error')) throw new Error(callback.searchParams.get('error') === 'access_denied' ? 'GitHub sign-in cancelled. You can try again.' : 'GitHub is temporarily unavailable. Try again.');
  const code = callback.searchParams.get('code');
  if (!code) throw new Error('Invalid sign-in response');
  return request<Session>('/auth/session', { method: 'POST', body: JSON.stringify({ code, verifier }) });
}
export const getUser = (token: string) => request<User>('/auth/me', { headers: { Authorization: `Bearer ${token}` } });
export const logout = (token: string) => request<void>('/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
