import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { Linking } from 'react-native';
import { AppProvider } from '../src/app/provider';
import { VoiceButton, VoiceFeedback, VoiceSettings } from '../src/features/discovery/components/voice-controls';

function controller() {
  return { consent: true, sheet: '', phase: 'recording', seconds: 26, error: '', transcript: '', permission: 'Off',
    start: jest.fn(async () => {}), release: jest.fn(async () => {}), cancel: jest.fn(async () => {}), accept: jest.fn(async () => {}), signOut: jest.fn(async () => {}), dismiss: jest.fn() };
}
test('accessible recording actions allow start, finish and cancellation without gestures', async () => {
  const voice = controller();
  const screen = await render(<AppProvider><VoiceButton voice={voice} /></AppProvider>);
  const mic = screen.getByRole('button');
  await fireEvent(mic, 'accessibilityAction', { nativeEvent: { actionName: 'record' } });
  expect(voice.start).toHaveBeenCalled();
  await fireEvent(mic, 'accessibilityAction', { nativeEvent: { actionName: 'finish' } });
  expect(voice.release).toHaveBeenCalled();
  await fireEvent(mic, 'accessibilityAction', { nativeEvent: { actionName: 'cancel' } });
  await fireEvent(mic, 'touchCancel');
  expect(voice.cancel).toHaveBeenCalledTimes(2);
});
test('recording countdown and visible cancel are usable; errors retain readable copy', async () => {
  const voice = controller(); voice.error = 'Try again or type your idea.';
  const screen = await render(<AppProvider><VoiceFeedback voice={voice} /></AppProvider>);
  expect(screen.getByText('26s · 4 seconds left')).toBeTruthy();
  await fireEvent.press(screen.getByText('Cancel recording'));
  expect(voice.cancel).toHaveBeenCalled();
  expect(screen.getByRole('alert')).toBeTruthy();
});
test('phone settings failure does not crash the voice settings screen', async () => {
  jest.spyOn(Linking, 'openSettings').mockRejectedValueOnce(new Error('unavailable'));
  const screen = await render(<AppProvider><VoiceSettings voice={controller()} speech={{ enabled: true, ready: true, setEnabled: jest.fn(), playing: false, tip: false, play: jest.fn(async () => {}), stop: jest.fn(), signOut: jest.fn(async () => {}) }} onBack={jest.fn()} /></AppProvider>);
  await fireEvent.press(screen.getByText('Open phone settings'));
  expect(screen.getByText('Microphone: Off')).toBeTruthy();
  jest.restoreAllMocks();
});
