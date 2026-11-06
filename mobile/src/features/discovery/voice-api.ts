import { fetch } from 'expo/fetch';
import { File } from 'expo-file-system';
import { authConfig } from '../../config/auth';
import { voiceConfig } from '../../config/voice';

export class VoiceError extends Error {
  constructor(public code: string, public retryable: boolean) {
    const message = code === 'VOICE_AUTH_REQUIRED' ? 'Sign in again to use voice.'
      : code === 'VOICE_TOO_LONG' ? 'Record up to 30 seconds, or type your idea.'
      : code === 'VOICE_TOO_LARGE' ? 'Recording is too large. Try a shorter idea.'
      : retryable ? "We couldn't catch that. Try again or type your idea."
      : 'Voice is unavailable. Type your idea.';
    super(message);
  }
}

export async function uploadRecording(uri: string, token: string, signal: AbortSignal): Promise<string> {
  const file = new File(uri);
  if (file.size > voiceConfig.maxBytes) throw new VoiceError('VOICE_TOO_LARGE', false);
  if (!file.size) throw new VoiceError('VOICE_INVALID_AUDIO', true);
  const body = await file.bytes();
  if (signal.aborted) throw new VoiceError('VOICE_CANCELLED', false);
  if (body.byteLength > voiceConfig.maxBytes) throw new VoiceError('VOICE_TOO_LARGE', false);
  const response = await fetch(`${authConfig.apiUrl}/v1/voice/transcribe`, {
    method: 'POST', body, signal,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'audio/m4a' },
  });
  const raw = await response.text();
  if (raw.length > voiceConfig.maxResponseChars) throw new VoiceError('VOICE_UNAVAILABLE', true);
  let data;
  try { data = JSON.parse(raw); } catch { throw new VoiceError('VOICE_UNAVAILABLE', true); }
  if (!response.ok) throw new VoiceError(
    typeof data?.detail?.code === 'string' ? data.detail.code : 'VOICE_UNAVAILABLE',
    data?.detail?.retryable === true,
  );
  if (typeof data?.transcript !== 'string' || data.transcript.trim().length < 2 || data.transcript.length > 1000) {
    throw new VoiceError('VOICE_NO_SPEECH', true);
  }
  return data.transcript.trim();
}
