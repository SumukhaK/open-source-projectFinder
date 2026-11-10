import { act, renderHook, waitFor } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { AppState, AppStateStatus } from 'react-native';
import { AudioModule } from 'expo-audio';
import { File } from 'expo-file-system';
import { useVoiceInput } from '../src/features/discovery/use-voice-input';
import { uploadRecording, VoiceError } from '../src/features/discovery/voice-api';

jest.mock('../src/features/discovery/voice-api', () => ({ ...jest.requireActual('../src/features/discovery/voice-api'), uploadRecording: jest.fn() }));
// NativeAudioModule declares this constructor; the import plugin cannot resolve it.
// eslint-disable-next-line import/namespace
const { AudioRecorder } = AudioModule;
const key = 'reporadar.voice.123.consent';
beforeEach(async () => {
  jest.clearAllMocks();
  jest.spyOn(AppState, 'addEventListener').mockImplementation(() => ({ remove: jest.fn() }));
  await AsyncStorage.clear();
  jest.mocked(uploadRecording).mockResolvedValue('find maps');
});
const consented = async () => {
  await AsyncStorage.setItem(key, 'yes');
  const hook = await renderHook(() => useVoiceInput('123', 'session'));
  await waitFor(() => expect(hook.result.current.consent).toBe(true));
  return hook;
};

test('consent precedes permission and Continue never starts a released hold', async () => {
  const hook = await renderHook(() => useVoiceInput('123', 'session'));
  await act(async () => { await hook.result.current.start(); });
  expect(hook.result.current.sheet).toBe('consent');
  expect(AudioModule.requestRecordingPermissionsAsync).not.toHaveBeenCalled();
  await act(async () => { await hook.result.current.accept(); });
  expect(AudioModule.requestRecordingPermissionsAsync).toHaveBeenCalled();
  expect(AudioRecorder).not.toHaveBeenCalled();
  expect(await AsyncStorage.getItem(key)).toBe('yes');
});

test('release uploads once and deletes the local recording', async () => {
  const hook = await consented();
  await act(async () => { await hook.result.current.start(); });
  expect(hook.result.current.phase).toBe('recording');
  await act(async () => { await hook.result.current.release(); await hook.result.current.release(); });
  expect(hook.result.current.transcript).toBe('find maps');
  expect(uploadRecording).toHaveBeenCalledTimes(1);
  expect(jest.mocked(File).mock.results.at(-1)?.value.delete).toHaveBeenCalled();
});

test.each([false, true])('permission granted=%s after release updates permission without recording', async granted => {
  jest.mocked(AudioModule.getRecordingPermissionsAsync).mockResolvedValueOnce({ granted: !granted } as never);
  const hook = await consented();
  await waitFor(() => expect(hook.result.current.permission).toBe(granted ? 'Off' : 'Allowed'));
  let resolve!: (value: Awaited<ReturnType<typeof AudioModule.requestRecordingPermissionsAsync>>) => void;
  jest.mocked(AudioModule.requestRecordingPermissionsAsync).mockImplementationOnce(() => new Promise(r => { resolve = r; }));
  let start!: Promise<void>;
  await act(async () => { start = hook.result.current.start(); });
  await act(async () => { void hook.result.current.release(); resolve({ granted } as never); await start; });
  expect(hook.result.current.permission).toBe(granted ? 'Allowed' : 'Off');
  expect(hook.result.current.sheet).toBe(granted ? '' : 'denied');
  expect(hook.result.current.phase).toBe('idle');
  expect(AudioRecorder).not.toHaveBeenCalled();
  expect(uploadRecording).not.toHaveBeenCalled();
});

test('denied permission retains the text path and shows the settings sheet', async () => {
  const hook = await consented();
  jest.mocked(AudioModule.requestRecordingPermissionsAsync).mockResolvedValueOnce({ granted: false } as never);
  await act(async () => { await hook.result.current.start(); });
  expect(hook.result.current.sheet).toBe('denied');
  expect(uploadRecording).not.toHaveBeenCalled();
});

test.each(['cancel', 'signOut', 'unmount', 'background'])('%s cancels recording and deletes the file without upload', async action => {
  let background!: (state: AppStateStatus) => void;
  const subscription = jest.spyOn(AppState, 'addEventListener').mockImplementation((_, fn) => { background = fn; return { remove: jest.fn() }; });
  const hook = await consented();
  await act(async () => { await hook.result.current.start(); });
  await act(async () => {
    if (action === 'unmount') await hook.unmount();
    else if (action === 'background') background('background');
    else if (action === 'signOut') await hook.result.current.signOut();
    else await hook.result.current.cancel();
  });
  await waitFor(() => expect(jest.mocked(File).mock.results.at(-1)?.value.delete).toHaveBeenCalled());
  expect(uploadRecording).not.toHaveBeenCalled();
  if (action === 'signOut') expect(await AsyncStorage.getItem(key)).toBeNull();
  subscription.mockRestore();
});

test.each(['signOut', 'unmount', 'background'])('late upload after %s is aborted and cannot populate transcript', async action => {
  let background!: (state: AppStateStatus) => void;
  jest.spyOn(AppState, 'addEventListener').mockImplementation((_, fn) => { background = fn; return { remove: jest.fn() }; });
  await AsyncStorage.setItem(key, 'yes');
  const received = jest.fn();
  const hook = await renderHook(() => useVoiceInput('123', 'session', received));
  await waitFor(() => expect(hook.result.current.consent).toBe(true));
  let resolve!: (text: string) => void;
  jest.mocked(uploadRecording).mockImplementationOnce(() => new Promise(r => { resolve = r; }));
  await act(async () => { await hook.result.current.start(); });
  await act(async () => { void hook.result.current.release(); });
  await waitFor(() => expect(uploadRecording).toHaveBeenCalled());
  await act(async () => {
    if (action === 'signOut') void hook.result.current.signOut();
    else if (action === 'unmount') await hook.unmount();
    else background('background');
  });
  expect(jest.mocked(uploadRecording).mock.calls[0][2].aborted).toBe(true);
  expect(jest.mocked(File).mock.results.at(-1)?.value.delete).toHaveBeenCalled();
  await act(async () => { resolve('late private transcript'); });
  expect(hook.result.current.transcript).toBe('');
  expect(received).not.toHaveBeenCalled();
});

test('consent does not transfer to another account', async () => {
  await AsyncStorage.setItem(key, 'yes');
  const hook = await renderHook(() => useVoiceInput('456', 'other-session'));
  await act(async () => { await hook.result.current.start(); });
  expect(hook.result.current.sheet).toBe('consent');
});

test('microphone status refreshes after returning from phone settings', async () => {
  let changed!: (state: AppStateStatus) => void;
  jest.spyOn(AppState, 'addEventListener').mockImplementation((_, fn) => { changed = fn; return { remove: jest.fn() }; });
  const hook = await renderHook(() => useVoiceInput('123', 'session'));
  await waitFor(() => expect(hook.result.current.permission).toBe('Allowed'));
  await act(async () => { changed('background'); });
  jest.mocked(AudioModule.getRecordingPermissionsAsync).mockResolvedValueOnce({ granted: false } as never);
  await act(async () => { changed('active'); });
  expect(hook.result.current.permission).toBe('Off');
});

test('native and UI duration caps stop once at 30 seconds', async () => {
  const hook = await consented();
  jest.useFakeTimers();
  await act(async () => { await hook.result.current.start(); });
  const recorder = jest.mocked(AudioRecorder).mock.results.at(-1)?.value;
  expect(recorder.record).toHaveBeenCalledWith({ forDuration: 30 });
  recorder.isRecording = false; // Native forDuration already stopped capture.
  recorder.stop.mockRejectedValueOnce(new Error('Already stopped'));
  await act(async () => { jest.advanceTimersByTime(30000); });
  expect(uploadRecording).toHaveBeenCalledTimes(1);
  await act(async () => { await hook.result.current.release(); });
  expect(uploadRecording).toHaveBeenCalledTimes(1);
  jest.useRealTimers();
});

test('cancellation while recorder preparation is pending cleans up without recording', async () => {
  const hook = await consented();
  let prepared!: () => void;
  const recorder = { prepareToRecordAsync: jest.fn(() => new Promise<void>(r => { prepared = r; })), record: jest.fn(), stop: jest.fn(async () => {}), release: jest.fn(), uri: 'file:///cache/pending.m4a' };
  jest.mocked(AudioRecorder).mockImplementationOnce(() => recorder as never);
  await act(async () => { void hook.result.current.start(); });
  await act(async () => { void hook.result.current.cancel(); prepared(); });
  expect(recorder.record).not.toHaveBeenCalled();
  expect(uploadRecording).not.toHaveBeenCalled();
  expect(jest.mocked(File).mock.results.at(-1)?.value.delete).toHaveBeenCalled();
});

test('provider failure shows safe copy and still deletes the recording', async () => {
  const hook = await consented();
  jest.mocked(uploadRecording).mockRejectedValueOnce(new VoiceError('VOICE_UNAVAILABLE', true));
  await act(async () => { await hook.result.current.start(); await hook.result.current.release(); });
  expect(hook.result.current.error).toContain('Try again');
  expect(hook.result.current.transcript).toBe('');
  expect(jest.mocked(File).mock.results.at(-1)?.value.delete).toHaveBeenCalled();
});

test('recording preparation failure leaves voice idle with text fallback', async () => {
  const hook = await consented();
  jest.mocked(AudioRecorder).mockImplementationOnce(() => ({ prepareToRecordAsync: async () => { throw new Error('native private details'); }, release: jest.fn(), uri: null }) as never);
  await act(async () => { await hook.result.current.start(); });
  expect(hook.result.current.phase).toBe('idle');
  expect(hook.result.current.error).toContain('type your idea');
  expect(uploadRecording).not.toHaveBeenCalled();
});

test('permission failure on Continue never starts recording', async () => {
  const hook = await renderHook(() => useVoiceInput('123', 'session'));
  jest.mocked(AudioModule.requestRecordingPermissionsAsync).mockRejectedValueOnce(new Error('native failure'));
  await act(async () => { await hook.result.current.accept(); });
  expect(hook.result.current.error).toContain('type your idea');
  expect(AudioRecorder).not.toHaveBeenCalled();
});

test('upload timeout aborts the request and cleans up', async () => {
  const hook = await consented();
  jest.useFakeTimers();
  jest.mocked(uploadRecording).mockImplementationOnce((_, __, signal) => new Promise((_, reject) => {
    signal.addEventListener('abort', () => reject(new Error('timeout')));
  }));
  await act(async () => { await hook.result.current.start(); });
  await act(async () => { void hook.result.current.release(); });
  await act(async () => { jest.advanceTimersByTime(20000); });
  expect(hook.result.current.phase).toBe('idle');
  expect(hook.result.current.error).toContain('Try again');
  expect(jest.mocked(File).mock.results.at(-1)?.value.delete).toHaveBeenCalled();
  jest.useRealTimers();
});

test('storage and audio-mode failures do not strand the microphone', async () => {
  jest.mocked(AsyncStorage.getItem).mockRejectedValueOnce(new Error('storage'));
  const hook = await renderHook(() => useVoiceInput('123', 'session'));
  jest.mocked(AsyncStorage.setItem).mockRejectedValueOnce(new Error('storage'));
  await act(async () => { await hook.result.current.accept(); });
  await act(async () => { await hook.result.current.start(); await hook.result.current.cancel(); });
  expect(hook.result.current.phase).toBe('idle');
  expect(jest.mocked(File).mock.results.at(-1)?.value.delete).toHaveBeenCalled();
});


test('inactive during consent permission keeps the denied result', async () => {
  let changed!: (state: AppStateStatus) => void;
  jest.spyOn(AppState, 'addEventListener').mockImplementation((_, fn) => { changed = fn; return { remove: jest.fn() }; });
  const hook = await renderHook(() => useVoiceInput('123', 'session'));
  let resolve!: (value: Awaited<ReturnType<typeof AudioModule.requestRecordingPermissionsAsync>>) => void;
  jest.mocked(AudioModule.requestRecordingPermissionsAsync).mockImplementationOnce(() => new Promise(r => { resolve = r; }));
  let accepted!: Promise<void>;
  await act(async () => { accepted = hook.result.current.accept(); });
  await act(async () => { changed('inactive'); resolve({ granted: false } as never); await accepted; });
  expect(hook.result.current.permission).toBe('Off');
  expect(hook.result.current.sheet).toBe('denied');
});

test('same-account remount keeps consent until sign-out', async () => {
  const hook = await consented();
  await hook.unmount();
  expect(await AsyncStorage.getItem(key)).toBe('yes');
  const remount = await renderHook(() => useVoiceInput('123', 'session'));
  await waitFor(() => expect(remount.result.current.consent).toBe(true));
  await act(async () => { await remount.result.current.signOut(); });
  expect(await AsyncStorage.getItem(key)).toBeNull();
});
