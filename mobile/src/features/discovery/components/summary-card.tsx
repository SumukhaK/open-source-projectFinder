import React, { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Pressable, Text, View } from 'react-native';
import { discoveryConfig } from '../../../config/discovery';
import { getThemeColors } from '../../../config/branding';
import { useTheme } from '../../../lib/theme';
import { useVoiceOutput } from '../use-voice-output';
import { streamSummary } from '../summary-api';

export function SummaryCard({ names, token, fromVoice, speech }: { names: string[]; token: string; fromVoice: boolean; speech: ReturnType<typeof useVoiceOutput> }) {
  const [summaryId, setSummaryId] = useState<string | null>(null);
  const attempted = useRef(false);
  const { play, stop, ready } = speech;
  useEffect(() => () => stop(), [stop]);
  useEffect(() => {
    if (!summaryId || !fromVoice || !ready || attempted.current) return;
    attempted.current = true;
    void play(summaryId, true);
  }, [summaryId, fromVoice, ready, play]);
  const [text, setText] = useState('');
  const colors = getThemeColors(useTheme().mode);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => { controller.abort(); setText(''); }, discoveryConfig.summaryTimeoutMs);
    void streamSummary(names, token, controller.signal, value => {
      if (!controller.signal.aborted) setText(value);
    }).then(value => {
      if (!controller.signal.aborted) {
        setSummaryId(value.summaryId);
        AccessibilityInfo.announceForAccessibilityWithOptions(`AI summary. ${value.text}`, { queue: true });
      }
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
    {summaryId ? <Pressable accessibilityRole="button" accessibilityLabel={speech.playing ? 'Stop' : 'Read aloud'}
      onPress={() => speech.playing ? stop() : void play(summaryId, false)} style={{ minHeight: 48, justifyContent: 'center' }}>
      <Text style={{ color: colors.text }}>{speech.playing ? 'Stop' : 'Read aloud'}</Text>
    </Pressable> : null}
    {speech.tip ? <Text style={{ color: colors.muted }}>Turn this off in Profile › Voice</Text> : null}
  </View>;
}
