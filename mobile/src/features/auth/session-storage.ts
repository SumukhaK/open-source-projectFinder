import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { authConfig } from '../../config/auth';

let webToken: string | null = null;
export const readToken = () => Platform.OS === 'web' ? Promise.resolve(webToken) : SecureStore.getItemAsync(authConfig.sessionKey);
export const saveToken = (token: string) => {
  if (Platform.OS === 'web') { webToken = token; return Promise.resolve(); }
  return SecureStore.setItemAsync(authConfig.sessionKey, token, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
};
export const clearToken = () => {
  if (Platform.OS === 'web') { webToken = null; return Promise.resolve(); }
  return SecureStore.deleteItemAsync(authConfig.sessionKey);
};
