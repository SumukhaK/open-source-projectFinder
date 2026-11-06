import React, { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Linking, Modal, Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { branding, getThemeColors } from '../../../config/branding';
import { voiceConfig } from '../../../config/voice';
import { useReducedMotion } from '../../../hooks/use-reduced-motion';
import { useTheme } from '../../../lib/theme';
import { useVoiceOutput } from '../use-voice-output';
import { useVoiceInput } from '../use-voice-input';

type Voice = ReturnType<typeof useVoiceInput>;

export function VoiceButton({ voice }: { voice: Voice }) {
  const colors = getThemeColors(useTheme().mode);
  const reduced = useReducedMotion();
  const [opacity] = useState(() => new Animated.Value(1));
  const origin = useRef({ x: 0, y: 0 });
  const recording = voice.phase === 'recording';
  useEffect(() => {
    if (!recording || reduced) { opacity.setValue(1); return; }
    const pulse = Animated.loop(Animated.sequence([
      Animated.timing(opacity, { toValue: 0.4, duration: branding.pulseDuration, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      Animated.timing(opacity, { toValue: 1, duration: branding.pulseDuration, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
    ]));
    pulse.start();
    return () => pulse.stop();
  }, [recording, reduced, opacity]);
  return <Pressable accessibilityRole="button" accessibilityLabel="Hold to record your idea"
    accessibilityHint="Hold to speak, release to search. Slide away to cancel."
    accessibilityState={{ disabled: voice.phase === 'uploading', busy: voice.phase === 'preparing' }}
    disabled={voice.phase === 'uploading'}
    accessibilityActions={[{ name: 'record', label: 'Start recording' }, { name: 'finish', label: 'Finish recording and search' }, { name: 'cancel', label: 'Cancel recording' }]}
    onAccessibilityAction={event => {
      const action = event.nativeEvent.actionName;
      if (action === 'record') void voice.start();
      if (action === 'finish') void voice.release();
      if (action === 'cancel') void voice.cancel();
    }}
    onPressIn={event => { origin.current = { x: event?.nativeEvent?.pageX ?? 0, y: event?.nativeEvent?.pageY ?? 0 }; void voice.start(); }}
    onPressOut={() => void voice.release()}
    onTouchMove={event => {
      if (Math.hypot(event.nativeEvent.pageX - origin.current.x, event.nativeEvent.pageY - origin.current.y) > voiceConfig.cancelDistance) void voice.cancel();
    }}
    onTouchCancel={() => void voice.cancel()}
    style={[styles.mic, { backgroundColor: colors.surface }]}
  >
    <Animated.View pointerEvents="none" style={[styles.ring, { borderColor: colors.accent, opacity: recording ? opacity : 0 }]} />
    <Svg width={24} height={24} viewBox="0 0 24 24" accessible={false}>
      <Path d="M8 6a4 4 0 018 0v6a4 4 0 01-8 0V6zm-3 5v1a7 7 0 0014 0v-1M12 19v3m-4 0h8" fill="none" stroke={colors.text} strokeWidth={2} />
    </Svg>
  </Pressable>;
}

export function VoiceFeedback({ voice }: { voice: Voice }) {
  const colors = getThemeColors(useTheme().mode);
  const recording = voice.phase === 'recording';
  return <>
    {!voice.consent ? <Text style={{ color: colors.muted }}>Hold the mic to say your idea.</Text> : null}
    {recording ? <>
      <Text accessibilityLiveRegion="polite" style={{ color: colors.text }}>{voice.seconds}s · {voice.seconds >= 25 ? `${30 - voice.seconds} seconds left` : 'Let go to search · Slide away to cancel'}</Text>
      <Pressable accessibilityRole="button" onPress={() => void voice.cancel()} style={styles.button}><Text style={{ color: colors.text }}>Cancel recording</Text></Pressable>
    </> : null}
    {voice.phase === 'preparing' || voice.phase === 'uploading' ? <Text accessibilityLiveRegion="polite" style={{ color: colors.muted }}>{voice.phase === 'preparing' ? 'Preparing microphone' : 'Turning speech into text'}</Text> : null}
    {voice.error ? <Text accessibilityRole="alert" style={{ color: colors.text }}>{voice.error}</Text> : null}
    <Modal visible={!!voice.sheet} transparent animationType="fade" onRequestClose={voice.dismiss}
      onShow={() => AccessibilityInfo.announceForAccessibility(voice.sheet === 'consent' ? 'Search by voice' : 'Microphone is off for RepoRadar')}>
      <View style={[styles.backdrop, { backgroundColor: colors.background }]}>
        <View accessibilityViewIsModal style={[styles.sheet, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <Text accessibilityRole="header" style={[styles.heading, { color: colors.text }]}>{voice.sheet === 'consent' ? 'Search by voice' : 'Microphone is off for RepoRadar'}</Text>
          <Text style={{ color: colors.text }}>{voice.sheet === 'consent'
            ? 'Hold the mic and describe your idea. Let go to search. You’ll see what we heard and can edit it. Your audio goes through our server to Deepgram to become text; the audio and transcript are not saved. Continue to allow the microphone, then hold the mic again.'
            : 'Allow microphone access in phone settings, or keep typing your idea.'}</Text>
          <Pressable accessibilityRole="button" style={styles.button} onPress={() => {
            if (voice.sheet === 'consent') void voice.accept();
            else void Linking.openSettings().catch(() => {});
          }}><Text style={{ color: colors.text }}>{voice.sheet === 'consent' ? 'Continue' : 'Open phone settings'}</Text></Pressable>
          <Pressable accessibilityRole="button" style={styles.button} onPress={voice.dismiss}><Text style={{ color: colors.text }}>Not now</Text></Pressable>
        </View>
      </View>
    </Modal>
  </>;
}

export function VoiceSettings({ voice, speech, onBack }: { voice: Voice; speech: ReturnType<typeof useVoiceOutput>; onBack: () => void }) {
  const colors = getThemeColors(useTheme().mode);
  const [help, setHelp] = useState(false);
  return <View style={styles.settings}>
    <Pressable accessibilityRole="button" style={styles.button} onPress={() => help ? setHelp(false) : onBack()}><Text style={{ color: colors.text }}>{help ? 'Back to Voice' : 'Back to Profile'}</Text></Pressable>
    <Text accessibilityRole="header" style={[styles.heading, { color: colors.text }]}>{help ? 'How voice works' : 'Voice'}</Text>
    {help ? <Text style={{ color: colors.text }}>Audio is sent through our server to Deepgram to become text. The recording is removed after upload or cancellation; audio and transcript are not saved by the app or server. Your words appear in the idea box, where you can edit them. Projects come from the same search as typed ideas. AI summaries describe only listed results and can be imperfect. Read summaries aloud controls automatic speech after voice searches. Typed searches never speak automatically; use Read aloud on a summary to hear it. To stop using voice, type instead or turn off microphone access in phone settings.</Text> : <>
      <Text style={{ color: colors.text }}>Read summaries aloud</Text>
      <Text style={{ color: colors.muted }}>After a voice search, hear a short summary. The list always shows.</Text>
      <Switch accessibilityLabel="Read summaries aloud" value={speech.enabled} disabled={!speech.ready} onValueChange={speech.setEnabled} style={{ minHeight: 48 }} />
      <Text style={{ color: colors.text }}>Microphone: {voice.permission}</Text>
      <Pressable accessibilityRole="button" style={styles.button} onPress={() => void Linking.openSettings().catch(() => {})}><Text style={{ color: colors.text }}>Open phone settings</Text></Pressable>
      <Pressable accessibilityRole="button" style={styles.button} onPress={() => setHelp(true)}><Text style={{ color: colors.text }}>How voice works</Text></Pressable>
    </>}
  </View>;
}

const styles = StyleSheet.create({
  mic: { position: 'absolute', right: 8, top: 8, width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  ring: { position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, borderWidth: 2, borderRadius: 24 },
  button: { minHeight: 48, justifyContent: 'center', padding: 8 },
  backdrop: { flex: 1, justifyContent: 'flex-end', padding: 20 },
  sheet: { padding: 24, gap: 16, borderRadius: 16, borderWidth: 1 },
  heading: { fontSize: 22, lineHeight: 28, fontWeight: '600' },
  settings: { gap: 16 },
});
