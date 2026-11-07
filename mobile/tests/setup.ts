jest.mock('@react-native-async-storage/async-storage', () =>
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

jest.mock('react-native-safe-area-context', () =>
  jest.requireActual('react-native-safe-area-context/jest/mock').default
);

jest.mock('expo-audio', () => ({
  createAudioPlayer: jest.fn(() => {
    let listener: (status: unknown) => void = () => {};
    return { play: jest.fn(), pause: jest.fn(), release: jest.fn(),
      addListener: jest.fn((_, fn) => { listener = fn; return { remove: jest.fn() }; }),
      emit: (status: unknown) => listener(status),
    };
  }),
  AudioModule: {
    getRecordingPermissionsAsync: jest.fn(async () => ({ granted: true, status: 'granted' })),
    requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true, status: 'granted' })),
    AudioRecorder: jest.fn(() => ({
      prepareToRecordAsync: jest.fn(async () => undefined), record: jest.fn(),
      stop: jest.fn(async () => undefined), release: jest.fn(), uri: 'file:///cache/voice.m4a', isRecording: true,
    })),
  },
  RecordingPresets: { HIGH_QUALITY: { extension: '.m4a' } },
  setAudioModeAsync: jest.fn(async () => undefined),
}));
jest.mock('expo-haptics', () => ({ impactAsync: jest.fn(async () => undefined), ImpactFeedbackStyle: { Light: 'light' } }));
jest.mock('expo-file-system', () => ({ File: jest.fn(() => ({ size: 100, exists: true, bytes: jest.fn(async () => new Uint8Array([1, 2])), delete: jest.fn() })) }));
jest.mock('expo/fetch', () => ({ fetch: jest.fn() }));
