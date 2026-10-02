export type ThemeMode = 'light' | 'dark';
export type ThemePreference = ThemeMode | 'system';

export const branding = {
  name: 'RepoRadar',
  appearanceStorageKey: 'reporadar.appearance',
  pulseDuration: 800,
  mark: {
    left: 'M 30 28 L 10 50 L 30 72',
    right: 'M 70 28 L 90 50 L 70 72',
    north: '50,10 38,46 62,46',
    south: '38,54 62,54 50,90',
  },
  themes: {
    dark: {
      background: '#0B1220', surface: '#131F33', border: '#2A3B53',
      onAccent: '#0B1220', text: '#F4F7FC', muted: '#A9B8CE', accent: '#58A6FF',
      north: '#58A6FF', south: '#5578FF',
    },
    light: {
      background: '#F4F7FC', surface: '#FFFFFF', border: '#CCD6E5',
      onAccent: '#FFFFFF', text: '#13233D', muted: '#51617A', accent: '#245FCC',
      north: '#245FCC', south: '#263FA6',
    },
  },
} as const;
