import { useCallback, useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, AppState } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio';
import { voiceConfig } from '../../config/voice';
import { authConfig } from '../../config/auth';

export function useVoiceOutput(account: string, token: string) {
  const key = `${voiceConfig.consentPrefix}.${account}.readAloud`;
  const tipKey = `${voiceConfig.consentPrefix}.${account}.speechTip`;
  const [preference, setPreference] = useState({ account: '', enabled: true, ready: false });
  const [playing, setPlaying] = useState(false);
  const [tip, setTip] = useState(false);
  const tipSeen = useRef(false);
  const mounted = useRef(true);
  const signedOut = useRef(false);
  const sequence = useRef(0);
  const writes = useRef(Promise.resolve());
  const current = useRef<ReturnType<typeof createAudioPlayer> | null>(null);
  const subscription = useRef<{ remove(): void } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const active = useRef(AppState.currentState === 'active');
  const ready = preference.account === account && preference.ready;
  const enabled = preference.account === account ? preference.enabled : true;

  const stop = useCallback(() => {
    sequence.current += 1;
    clearTimeout(timer.current);
    subscription.current?.remove(); subscription.current = null;
    const player = current.current; current.current = null;
    if (player) {
      try { player.pause(); } catch { /* Native failure must not affect search. */ }
      try { player.release(); } catch { /* Already released by the OS. */ }
    }
    if (mounted.current) { setPlaying(false); setTip(false); }
  }, []);

  useEffect(() => {
    mounted.current = true; signedOut.current = false;
    let live = true;
    void Promise.all([AsyncStorage.getItem(key), AsyncStorage.getItem(tipKey)]).then(([value, seen]) => {
      if (!live || signedOut.current) return;
      tipSeen.current = seen === 'yes';
      setPreference({ account, enabled: value !== 'false', ready: true });
    }).catch(() => { if (live) setPreference({ account, enabled: false, ready: true }); });
    const listener = AppState.addEventListener('change', state => {
      active.current = state === 'active';
      if (state === 'background') stop();
    });
    return () => { live = false; mounted.current = false; stop(); listener.remove(); };
  }, [account, key, tipKey, stop]);

  const setEnabled = (value: boolean) => {
    stop();
    setPreference({ account, enabled: value, ready: true });
    writes.current = writes.current.then(() => AsyncStorage.setItem(key, String(value))).catch(() => {});
  };
  const signOut = async () => {
    signedOut.current = true; stop();
    await writes.current;
    await AsyncStorage.removeItem(key).catch(() => {});
  };

  const play = useCallback(async (id: string, automatic: boolean) => {
    stop();
    const version = sequence.current;
    const valid = () => mounted.current && !signedOut.current && version === sequence.current && active.current;
    if (!valid() || !id || (automatic && (!ready || !enabled))) return;
    try {
      if (automatic && await AccessibilityInfo.isScreenReaderEnabled()) return;
      if (!valid()) return;
      await setAudioModeAsync({ playsInSilentMode: false, shouldPlayInBackground: false, allowsRecording: false, interruptionMode: 'doNotMix' });
      if (!valid()) return;
      const player = createAudioPlayer({ uri: `${authConfig.apiUrl}/v1/voice/speech/${encodeURIComponent(id)}`, headers: { Authorization: `Bearer ${token}` } }, { downloadFirst: false });
      current.current = player;
      subscription.current = player.addListener('playbackStatusUpdate', status => {
        if (!valid()) return;
        if (status.error || status.didJustFinish) { stop(); return; }
        if (status.playing && automatic && !tipSeen.current) {
          tipSeen.current = true; setTip(true);
          writes.current = writes.current.then(() => AsyncStorage.setItem(tipKey, 'yes')).catch(() => {});
        }
      });
      timer.current = setTimeout(stop, voiceConfig.speechMaxMs);
      setPlaying(true); player.play();
    } catch { if (version === sequence.current) stop(); }
  }, [enabled, ready, stop, tipKey, token]);
  return { enabled, ready, setEnabled, playing, tip, play, stop, signOut };
}
