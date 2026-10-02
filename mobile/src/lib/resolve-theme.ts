import { ColorSchemeName } from 'react-native';
import { ThemeMode, ThemePreference } from '../config/branding';

export function resolveTheme(preference: ThemePreference, system: ColorSchemeName | null | undefined): ThemeMode {
  return preference === 'system' ? (system === 'light' ? 'light' : 'dark') : preference;
}
