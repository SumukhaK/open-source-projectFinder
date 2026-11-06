import { act, renderHook, waitFor } from '@testing-library/react-native';
import { AccessibilityInfo, AppState, AppStateStatus } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio';
import { useVoiceOutput } from '../src/features/discovery/use-voice-output';

beforeEach(async () => {
  jest.clearAllMocks(); await AsyncStorage.clear(); AppState.currentState = 'active';
  jest.spyOn(AccessibilityInfo, 'isScreenReaderEnabled').mockResolvedValue(false);
});
afterEach(() => { jest.restoreAllMocks(); jest.useRealTimers(); });
async function ready() {
  const hook = await renderHook(() => useVoiceOutput('123', 'session'));
  await waitFor(() => expect(hook.result.current.ready).toBe(true));
  return hook;
}

test.each(['stop', 'signOut', 'unmount'])('%s during audio-mode setup prevents late playback', async action => {
  const hook = await ready();
  let resolve!: () => void;
  jest.mocked(setAudioModeAsync).mockImplementationOnce(() => new Promise<void>(done => { resolve = done; }));
  let playing!: Promise<void>;
  await act(async () => { playing = hook.result.current.play('id', true); });
  if (action === 'unmount') await hook.unmount();
  await act(async () => {
    if (action === 'signOut') await hook.result.current.signOut();
    else if (action === 'stop') hook.result.current.stop();
    resolve(); await playing;
  });
  expect(createAudioPlayer).not.toHaveBeenCalled();
});

test('a pending accessibility check cannot revive cancelled playback', async () => {
  const hook = await ready();
  let resolve!: (enabled: boolean) => void;
  jest.mocked(AccessibilityInfo.isScreenReaderEnabled).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  let playing!: Promise<void>;
  await act(async () => { playing = hook.result.current.play('id', true); });
  await act(async () => { hook.result.current.stop(); resolve(false); await playing; });
  expect(createAudioPlayer).not.toHaveBeenCalled();
});

test('native creation failure and preference read failure stay silent', async () => {
  jest.mocked(AsyncStorage.getItem).mockRejectedValueOnce(new Error('disk'));
  const hook = await ready();
  expect(hook.result.current.enabled).toBe(false);
  await act(async () => { await hook.result.current.play('id', true); });
  expect(createAudioPlayer).not.toHaveBeenCalled();
  jest.mocked(createAudioPlayer).mockImplementationOnce(() => { throw new Error('native'); });
  await act(async () => { await hook.result.current.play('id', false); });
  expect(hook.result.current.playing).toBe(false);
});

test('stalled playback is bounded and releases native resources', async () => {
  const hook = await ready(); jest.useFakeTimers();
  await act(async () => { await hook.result.current.play('id', false); });
  const player = jest.mocked(createAudioPlayer).mock.results.at(-1)!.value;
  await act(async () => { jest.advanceTimersByTime(120000); });
  expect(player.release).toHaveBeenCalledTimes(1);
  expect(hook.result.current.playing).toBe(false);
});

test('sign-out waits for the pending preference write before removing it', async () => {
  const hook = await ready();
  let resolve!: () => void;
  const original = AsyncStorage.setItem;
  jest.mocked(AsyncStorage.setItem).mockImplementationOnce((key, value) => new Promise<void>(done => { resolve = () => { void original(key, value).then(done); }; }));
  await act(async () => { hook.result.current.setEnabled(false); });
  let cleared!: Promise<void>;
  await act(async () => { cleared = hook.result.current.signOut(); resolve(); await cleared; });
  expect(await AsyncStorage.getItem('reporadar.voice.123.readAloud')).toBeNull();
});


test.each([{ didJustFinish: true }, { error: 'native failure' }])('inactive playback terminal event %j releases immediately', async status => {
  let changed!: (state: AppStateStatus) => void;
  jest.spyOn(AppState, 'addEventListener').mockImplementation((_, fn) => { changed = fn; return { remove: jest.fn() }; });
  const hook = await ready();
  await act(async () => { await hook.result.current.play('id', false); });
  const player = jest.mocked(createAudioPlayer).mock.results.at(-1)!.value as unknown as { emit: (value: object) => void; release: jest.Mock };
  await act(async () => { changed('inactive'); player.emit(status); });
  expect(player.release).toHaveBeenCalledTimes(1);
  expect(hook.result.current.playing).toBe(false);
});
