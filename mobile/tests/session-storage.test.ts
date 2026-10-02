import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { readToken, saveToken, clearToken } from '../src/features/auth/session-storage';
jest.mock('expo-secure-store', () => ({ getItemAsync: jest.fn(), setItemAsync: jest.fn(), deleteItemAsync: jest.fn(), WHEN_UNLOCKED_THIS_DEVICE_ONLY: 1 }));
const original = Object.getOwnPropertyDescriptor(Platform, 'OS')!;
let mode = 'ios';
beforeAll(() => Object.defineProperty(Platform, 'OS', { configurable: true, get: () => mode }));
afterAll(() => Object.defineProperty(Platform, 'OS', original));
beforeEach(() => { mode = 'ios'; jest.clearAllMocks(); });
test('native tokens use protected device-only secure storage', async () => {
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue('saved');
  await saveToken('saved');
  expect(await readToken()).toBe('saved');
  expect(SecureStore.setItemAsync).toHaveBeenCalledWith('reporadar.session', 'saved', { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
  await clearToken(); expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('reporadar.session');
});
test('web preview keeps tokens only in memory and can clear them', async () => {
  mode = 'web'; await saveToken('memory'); expect(await readToken()).toBe('memory');
  await clearToken(); expect(await readToken()).toBeNull();
  expect(SecureStore.setItemAsync).not.toHaveBeenCalled();
});
