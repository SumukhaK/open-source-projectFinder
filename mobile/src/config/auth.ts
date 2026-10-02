export const authConfig = {
  apiUrl: process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000',
  redirectUri: 'reporadar://auth/callback',
  sessionKey: 'reporadar.session',
  timeoutMs: 15000,
};
