import React, { useEffect, useState } from 'react';
import { AccessibilityInfo, Text, View } from 'react-native';
import { discoveryConfig } from '../../../config/discovery';
import { getThemeColors } from '../../../config/branding';
import { useTheme } from '../../../lib/theme';
import { streamSummary } from '../summary-api';

export function SummaryCard({ names, token }: { names: string[]; token: string }) {
  const [text, setText] = useState('');
  const colors = getThemeColors(useTheme().mode);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => { controller.abort(); setText(''); }, discoveryConfig.summaryTimeoutMs);
    void streamSummary(names, token, controller.signal, value => {
      if (!controller.signal.aborted) setText(value);
    }).then(value => {
      if (!controller.signal.aborted) AccessibilityInfo.announceForAccessibilityWithOptions(`AI summary. ${value}`, { queue: true });
    }).catch(() => { if (!controller.signal.aborted) setText(''); })
      .finally(() => clearTimeout(timer));
    return () => { clearTimeout(timer); controller.abort(); };
  }, [names, token]);
  if (!text) return null;
  // Static text: no animation, and only the completed summary is announced.
  return <View style={{ padding: 16, gap: 8, borderRadius: 16, borderWidth: 1, backgroundColor: colors.surface, borderColor: colors.border }}>
    <Text accessibilityRole="header" style={{ color: colors.text, fontSize: 17, fontWeight: '600' }}>Summary</Text>
    <Text style={{ color: colors.text, alignSelf: 'flex-start', paddingHorizontal: 8, borderWidth: 1, borderRadius: 8, borderColor: colors.border }}>AI</Text>
    <Text style={{ color: colors.muted }}>Based only on the results below</Text>
    <Text style={{ color: colors.text, fontSize: 16, lineHeight: 24 }}>{text}</Text>
  </View>;
}
