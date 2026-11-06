import { fetch } from 'expo/fetch';
import { File } from 'expo-file-system';
import { uploadRecording } from '../src/features/discovery/voice-api';

beforeEach(() => { jest.clearAllMocks(); });

test('uploads raw M4A bytes with app authentication and never a provider key', async () => {
  jest.mocked(fetch).mockResolvedValue({ ok: true, text: async () => JSON.stringify({ transcript: 'find maps' }) } as Awaited<ReturnType<typeof fetch>>);
  expect(await uploadRecording('file:///cache/voice.m4a', 'session', new AbortController().signal)).toBe('find maps');
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/v1/voice/transcribe'), expect.objectContaining({
    method: 'POST', body: new Uint8Array([1, 2]), headers: { Authorization: 'Bearer session', 'Content-Type': 'audio/m4a' },
  }));
});

test.each([
  ['VOICE_TOO_LONG', false, 'Record up to 30 seconds'],
  ['VOICE_UNAVAILABLE', true, 'Try again'],
  ['VOICE_AUTH_REQUIRED', false, 'Sign in'],
])('maps %s without exposing provider detail', async (code, retryable, copy) => {
  jest.mocked(fetch).mockResolvedValue({ ok: false, text: async () => JSON.stringify({ detail: { code, retryable, message: 'private server detail' } }) } as Awaited<ReturnType<typeof fetch>>);
  await expect(uploadRecording('file:///cache/voice.m4a', 'session', new AbortController().signal)).rejects.toThrow(copy);
});

test('refuses an oversized recording before reading or uploading it', async () => {
  jest.mocked(File).mockImplementationOnce(() => ({ size: 1048577 }) as File);
  await expect(uploadRecording('file:///cache/voice.m4a', 'session', new AbortController().signal)).rejects.toThrow('Recording is too large');
  expect(fetch).not.toHaveBeenCalled();
});

test.each(['not json', '{}', JSON.stringify({ transcript: '' }), 'x'.repeat(8193)])('rejects unusable provider payload without exposing it', async raw => {
  jest.mocked(fetch).mockResolvedValue({ ok: true, text: async () => raw } as Awaited<ReturnType<typeof fetch>>);
  await expect(uploadRecording('file:///cache/voice.m4a', 'session', new AbortController().signal)).rejects.toThrow('Try again');
});

test('a cancelled file read never starts an upload', async () => {
  const controller = new AbortController(); controller.abort();
  await expect(uploadRecording('file:///cache/voice.m4a', 'session', controller.signal)).rejects.toThrow();
  expect(fetch).not.toHaveBeenCalled();
});
