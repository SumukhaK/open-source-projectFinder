import 'tsx/cjs';
import { ExpoConfig } from 'expo/config';
import { branding } from './src/config/branding';

const config: ExpoConfig = {
  name: branding.name,
  slug: 'reporadar',
  scheme: 'reporadar',
  version: '0.1.0',
  orientation: 'default',
  userInterfaceStyle: 'automatic',
  icon: './assets/branding/icon-dark.png',
  ios: {
    supportsTablet: true,
    icon: { light: './assets/branding/icon-light.png', dark: './assets/branding/icon-dark.png', tinted: './assets/branding/icon-tinted.png' },
  },
  android: {
    adaptiveIcon: {
      foregroundImage: './assets/branding/adaptive-foreground.png',
      backgroundColor: branding.themes.dark.background,
      monochromeImage: './assets/branding/adaptive-monochrome.png',
    },
  },
  web: { favicon: './assets/branding/icon-light.png' },
  plugins: [
    'expo-system-ui',
    'expo-secure-store',
    ['expo-splash-screen', {
      backgroundColor: branding.themes.light.background,
      image: './assets/branding/splash-light.png',
      imageWidth: 120,
      dark: { backgroundColor: branding.themes.dark.background, image: './assets/branding/splash-dark.png' },
      ios: {
        backgroundColor: branding.themes.light.background,
        image: './assets/branding/splash-empty.png',
        dark: { backgroundColor: branding.themes.dark.background, image: './assets/branding/splash-empty.png' },
      },
    }],
  ],
};
export default config;
