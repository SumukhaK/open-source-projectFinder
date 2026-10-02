import React, { useEffect, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Platform, StyleSheet, Text, View } from 'react-native';
import { branding, ThemeMode } from '../config/branding';
import { useReducedMotion } from '../hooks/use-reduced-motion';
import { BrandMark } from './brand-mark';

type Props = { mode: ThemeMode; size?: number; label?: string };

export function BrandLoader({ mode, size = 64, label = 'Loading' }: Props) {
  const [opacity] = useState(() => new Animated.Value(1));
  const reduced = useReducedMotion();
  useEffect(() => {
    if (Platform.OS !== 'web') AccessibilityInfo.announceForAccessibility(label);
  }, [label]);
  useEffect(() => {
    opacity.setValue(1);
    if (reduced) return;
    const animation = Animated.loop(Animated.sequence([
      Animated.timing(opacity, { toValue: 0.4, duration: branding.pulseDuration, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      Animated.timing(opacity, { toValue: 1, duration: branding.pulseDuration, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
    ]));
    animation.start();
    return () => { animation.stop(); opacity.setValue(1); };
  }, [opacity, reduced]);

  return <View style={styles.container} accessible accessibilityRole="progressbar"
    accessibilityLabel={label} accessibilityState={{ busy: true }} aria-busy accessibilityLiveRegion="polite" aria-live="polite">
    <View style={{ width: size, height: size }} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
      <BrandMark mode={mode} size={size} part="brackets" />
      <Animated.View style={[StyleSheet.absoluteFill, { opacity }]}>
        <BrandMark mode={mode} size={size} part="needle" />
      </Animated.View>
    </View>
    <Text accessible={false} style={[styles.label, { color: branding.themes[mode].muted }]}>{label}</Text>
  </View>;
}
const styles = StyleSheet.create({ container: { alignItems: 'center', gap: 14 }, label: { fontSize: 15 } });
