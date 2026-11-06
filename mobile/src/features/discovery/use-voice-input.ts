import { useEffect, useRef, useState } from 'react';
import { AppState, Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { AudioModule, RecordingPresets, setAudioModeAsync } from 'expo-audio';
import { File } from 'expo-file-system';
import * as Haptics from 'expo-haptics';
import { voiceConfig } from '../../config/voice';
import { uploadRecording, VoiceError } from './voice-api';
// Expo declares this runtime constructor in NativeAudioModule, not a JS named export.
// eslint-disable-next-line import/namespace
const { AudioRecorder } = AudioModule;

type Operation = {
  cancelled: boolean; held: boolean; started: boolean; ready: Promise<void>;
  recorder?: InstanceType<typeof AudioModule.AudioRecorder>; finishing?: Promise<void>;
  controller: AbortController; timer?: ReturnType<typeof setTimeout>;
  tick?: ReturnType<typeof setInterval>;
  stopped?: boolean; deleted?: boolean;
};

export function useVoiceInput(account: string, token: string, onTranscript?: (text: string) => void) {
  const [consent, setConsent] = useState(false);
  const [sheet, setSheet] = useState('');
  const [phase, setPhase] = useState('idle');
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState('');
  const [transcript, setTranscript] = useState('');
  const [permission, setPermission] = useState('Unknown');
  const mounted = useRef(true);
  const generation = useRef(0);
  const allowed = useRef(false);
  const operation = useRef<Operation | null>(null);
  const consentWrite = useRef(Promise.resolve());
  const transcriptCallback = useRef(onTranscript);
  useEffect(() => { transcriptCallback.current = onTranscript; }, [onTranscript]);
  const key = `${voiceConfig.consentPrefix}.${account}.consent`;
  const message = (failure: unknown) => {
    if (mounted.current) setError(failure instanceof VoiceError ? failure.message : "We couldn't catch that. Try again or type your idea.");
  };

  function removeFile(op: Operation) {
    if (op.deleted) return;
    const uri = op.recorder?.uri;
    if (uri) { const file = new File(uri); if (file.exists) file.delete(); }
    op.deleted = true;
  }

  function finish(op: Operation, send: boolean): Promise<void> {
    if (op.finishing) return op.finishing;
    op.held = false;
    clearTimeout(op.timer); clearInterval(op.tick);
    op.finishing = (async () => {
      await op.ready;
      try {
        if (op.recorder?.isRecording) await op.recorder.stop();
        op.stopped = true;
        const uri = op.recorder?.uri;
        if (send && op.started && !op.cancelled && uri) {
          if (mounted.current) setPhase('uploading');
          op.timer = setTimeout(() => op.controller.abort(), voiceConfig.uploadTimeoutMs);
          const text = await uploadRecording(uri, token, op.controller.signal);
          if (!op.cancelled && mounted.current) { setTranscript(text); transcriptCallback.current?.(text); }
        }
      } catch (failure) { if (!op.cancelled) message(failure); }
      finally {
        clearTimeout(op.timer);
        try {
          removeFile(op);
        } catch {
          if (mounted.current) setError('The recording could not be removed. Close voice and check device storage.');
        }
        op.recorder?.release();
        await setAudioModeAsync({ allowsRecording: false }).catch(() => {});
        if (operation.current === op) operation.current = null;
        if (mounted.current) setPhase('idle');
      }
    })();
    return op.finishing;
  }

  async function cancel() {
    const op = operation.current;
    if (!op) return;
    op.cancelled = true; op.held = false; op.controller.abort();
    if (op.stopped) { try { removeFile(op); } catch (failure) { message(failure); } }
    await finish(op, false);
  }
  async function release() {
    const op = operation.current;
    if (op) await finish(op, true);
  }
  async function start() {
    if (operation.current) return;
    setError(''); setTranscript('');
    if (Platform.OS === 'web') { setError('Voice recording is available in the phone app. Type your idea here.'); return; }
    if (!allowed.current) { setSheet('consent'); return; }
    const op: Operation = { cancelled: false, held: true, started: false, ready: Promise.resolve(), controller: new AbortController() };
    operation.current = op;
    setPhase('preparing');
    op.ready = (async () => {
      try {
        const permission = await AudioModule.requestRecordingPermissionsAsync();
        if (op.cancelled || !op.held) return;
        setPermission(permission.granted ? 'Allowed' : 'Off');
        if (!permission.granted) { setSheet('denied'); return; }
        await setAudioModeAsync({ allowsRecording: true, shouldPlayInBackground: false });
        if (op.cancelled || !op.held) return;
        const preset = RecordingPresets.HIGH_QUALITY;
        op.recorder = new AudioRecorder({ ...preset, ...(Platform.OS === 'android' ? preset.android : preset.ios) });
        await op.recorder.prepareToRecordAsync(preset);
        if (op.cancelled || !op.held) return;
        op.recorder.record({ forDuration: voiceConfig.maxSeconds });
        op.started = true;
        setPhase('recording'); setSeconds(0);
        void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
        const began = Date.now();
        op.tick = setInterval(() => { if (mounted.current) setSeconds(Math.min(voiceConfig.maxSeconds, Math.floor((Date.now() - began) / 1000))); }, 250);
        op.timer = setTimeout(() => { void finish(op, true); }, voiceConfig.maxSeconds * 1000);
      } catch (failure) { if (!op.cancelled) message(failure); }
    })();
    await op.ready;
    if (!op.started) await finish(op, false);
  }
  async function accept() {
    const version = ++generation.current;
    setSheet('');
    allowed.current = true; setConsent(true);
    consentWrite.current = AsyncStorage.setItem(key, 'yes').catch(() => {});
    try {
      const result = await AudioModule.requestRecordingPermissionsAsync();
      if (version !== generation.current || !mounted.current) return;
      setPermission(result.granted ? 'Allowed' : 'Off');
      if (!result.granted) setSheet('denied');
    } catch (failure) { if (version === generation.current) message(failure); }
  }
  async function signOut() {
    generation.current += 1; allowed.current = false;
    setConsent(false); setSheet(''); setTranscript('');
    void cancel();
    await consentWrite.current;
    await AsyncStorage.removeItem(key).catch(() => {});
  }
  const actions = useRef({ cancel, signOut });
  useEffect(() => { actions.current = { cancel, signOut }; });
  useEffect(() => {
    mounted.current = true;
    const version = ++generation.current;
    allowed.current = false;
    void AsyncStorage.getItem(key).then(value => {
      if (mounted.current && generation.current === version) { allowed.current = value === 'yes'; setConsent(value === 'yes'); }
    }).catch(() => {});
    const refreshPermission = () => {
      const currentVersion = generation.current;
      void AudioModule.getRecordingPermissionsAsync().then(value => {
        if (mounted.current && generation.current === currentVersion) setPermission(value.granted ? 'Allowed' : 'Off');
      }).catch(() => {});
    };
    refreshPermission();
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'background') { generation.current += 1; setSheet(''); void actions.current.cancel(); }
      else if (state === 'active') refreshPermission();
    });
    return () => {
      mounted.current = false; generation.current += 1;
      void actions.current.cancel(); subscription.remove();
    };
  }, [key, token]);
  return { consent, sheet, phase, seconds, error, transcript, permission, start, release, cancel, accept, signOut, dismiss: () => setSheet('') };
}
