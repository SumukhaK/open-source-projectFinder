import React from 'react';
import Svg, { Path, Polygon } from 'react-native-svg';
import { branding, getThemeColors, ThemeMode } from '../config/branding';

type Props = { mode: ThemeMode; size?: number; part?: 'all' | 'brackets' | 'needle' };

export function BrandMark({ mode, size = 64, part = 'all' }: Props) {
  const colors = getThemeColors(mode);
  const mark = branding.mark;
  return <Svg width={size} height={size} viewBox="0 0 100 100" accessible={false}>
    {part !== 'needle' && <>
      <Path d={mark.left} stroke={colors.accent} strokeWidth={10} strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <Path d={mark.right} stroke={colors.accent} strokeWidth={10} strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </>}
    {part !== 'brackets' && <>
      <Polygon points={mark.north} fill={colors.north} />
      <Polygon points={mark.south} fill={colors.south} />
    </>}
  </Svg>;
}
