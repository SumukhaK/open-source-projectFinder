import React from 'react';
import { spawn, ChildProcess } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
import net from 'node:net';
import { AccessibilityInfo } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { AuthScreen } from '../src/features/auth/components/auth-screen';
import { AppProvider } from '../src/app/provider';
import * as WebBrowser from 'expo-web-browser';

jest.mock('expo-web-browser', () => ({ openAuthSessionAsync: jest.fn() }));
// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('expo-crypto', () => ({ getRandomBytesAsync: async () => new Uint8Array(32).fill(1), digestStringAsync: async (_: string, value: string) => require('node:crypto').createHash('sha256').update(value).digest('base64'), CryptoDigestAlgorithm: { SHA256: 'SHA-256' }, CryptoEncoding: { BASE64: 'base64' } }));
jest.mock('../src/config/auth', () => ({ authConfig: { get apiUrl() { return process.env.E2E_API_URL; }, redirectUri: 'reporadar://auth/callback', sessionKey: 'test', timeoutMs: 15000 } }));
jest.mock('../src/features/auth/session-storage', () => {
  let token: string | null = null;
  return { readToken: async () => token, saveToken: async (value: string) => { token = value; }, clearToken: async () => { token = null; } };
});

// Real HTTP adapter avoids React Native's mocked XMLHttpRequest in Jest.
function request(url: string, init: RequestInit = {}): Promise<Response> {
  return new Promise((resolve, reject) => {
    const req = http.request(url, { method: init.method ?? 'GET', headers: init.headers as http.OutgoingHttpHeaders }, res => {
      let body = '';
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => resolve({ ok: (res.statusCode ?? 500) < 400, status: res.statusCode, headers: { get: (key: string) => res.headers[key.toLowerCase()] ?? null }, json: async () => JSON.parse(body) } as unknown as Response));
    });
    req.on('error', reject); req.setTimeout(15000, () => req.destroy(new Error('timeout')));
    if (init.body) req.write(init.body); req.end();
  });
}
const suite = process.env.RUN_AUTH_E2E === '1' ? describe : describe.skip;
suite('mobile UI through real FastAPI HTTP with simulated GitHub', () => {
  let server: ChildProcess;
  let originalFetch: typeof fetch;
  beforeAll(async () => {
    const port = await new Promise<number>(resolve => {
      const socket = net.createServer(); socket.listen(0, '127.0.0.1', () => { const address = socket.address() as net.AddressInfo; socket.close(() => resolve(address.port)); });
    });
    process.env.E2E_API_URL = `http://127.0.0.1:${port}`;
    const backend = path.resolve(__dirname, '../../backend');
    const python = process.env.PYTHON_EXECUTABLE ?? path.join(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    server = spawn(python, ['tests/e2e_server.py', String(port)], { cwd: backend, stdio: 'pipe' });
    let failure = ''; server.stderr?.on('data', data => { failure += data.toString(); });
    server.on('error', error => { failure += error.message; });
    let healthy = false;
    for (let i = 0; i < 100; i++) {
      try { await request(`${process.env.E2E_API_URL}/health`); healthy = true; break; } catch { await new Promise(resolve => setTimeout(resolve, 100)); }
    }
    if (!healthy) throw new Error(`Test backend failed to start: ${failure}`);
    originalFetch = global.fetch; global.fetch = request as typeof fetch;
    jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);
    jest.mocked(WebBrowser.openAuthSessionAsync).mockImplementation(async url => {
      const state = new URL(url).searchParams.get('state');
      const callback = await request(`${process.env.E2E_API_URL}/auth/github/callback?state=${state}&code=test-code`);
      return { type: 'success', url: callback.headers.get('location')! };
    });
  }, 20000);
  afterAll(() => { global.fetch = originalFetch; server?.kill(); delete process.env.E2E_API_URL; });
  test('signup, persisted-session restore, logout and returning login', async () => {
    let screen = await render(<AppProvider><AuthScreen /></AppProvider>);
    await waitFor(() => expect(screen.getByText('Continue with GitHub')).toBeTruthy());
    await fireEvent.press(screen.getByText('Continue with GitHub'));
    await waitFor(() => expect(screen.getByText('Signed in as @octocat')).toBeTruthy());
    await screen.unmount();
    screen = await render(<AppProvider><AuthScreen /></AppProvider>);
    await waitFor(() => expect(screen.getByText('Signed in as @octocat')).toBeTruthy());
    await fireEvent.press(screen.getByText('Sign out'));
    await waitFor(() => expect(screen.getByText('Continue with GitHub')).toBeTruthy());
    await fireEvent.press(screen.getByText('Continue with GitHub'));
    await waitFor(() => expect(screen.getByText('Signed in as @octocat')).toBeTruthy());
    await screen.unmount();
  });
});
