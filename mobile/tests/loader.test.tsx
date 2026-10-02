import React from 'react';
import { AccessibilityInfo, Animated } from 'react-native';
import { render, waitFor, act } from '@testing-library/react-native';
import { BrandLoader } from '../src/components/brand-loader';

beforeEach(() => { jest.restoreAllMocks(); });

test('loads with an accessible label and stops animation on unmount', async () => {
  jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(false);
  const start = jest.fn(); const stop = jest.fn();
  jest.spyOn(Animated, 'loop').mockReturnValue({ start, stop, reset: jest.fn() });
  const screen = await render(<BrandLoader mode="dark" label="Finding repositories" />);
  expect(screen.getByRole('progressbar').props.accessibilityLabel).toBe('Finding repositories');
  await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
  await screen.unmount();
  expect(stop).toHaveBeenCalledTimes(1);
});

test('Reduce Motion disables movement and responds to settings changes', async () => {
  jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);
  let change: (enabled: boolean) => void = () => {};
  const remove = jest.fn();
  jest.spyOn(AccessibilityInfo, 'addEventListener').mockImplementation(((event: string, handler: (enabled: boolean) => void) => {
    if (event === 'reduceMotionChanged') change = handler as typeof change;
    return { remove };
  }) as unknown as typeof AccessibilityInfo.addEventListener);
  const start = jest.fn(); const stop = jest.fn();
  const loop = jest.spyOn(Animated, 'loop').mockReturnValue({ start, stop, reset: jest.fn() });
  const screen = await render(<BrandLoader mode="light" />);
  await act(async () => {});
  expect(loop).not.toHaveBeenCalled();
  await act(async () => change(false));
  await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
  await act(async () => change(true));
  expect(stop).toHaveBeenCalledTimes(1);
  await screen.unmount(); expect(remove).toHaveBeenCalled();
});

test('defaults to a static mark when motion settings cannot be read', async () => {
  jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockRejectedValue(new Error('unavailable'));
  const loop = jest.spyOn(Animated, 'loop');
  await render(<BrandLoader mode="dark" />);
  await act(async () => {});
  expect(loop).not.toHaveBeenCalled();
});
