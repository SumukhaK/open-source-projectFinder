import React from 'react';
import { Text } from 'react-native';
import { render, fireEvent } from '@testing-library/react-native';
import { CrashBoundary } from '../src/components/crash-boundary';

test('render crashes recover without logging private error contents', async () => {
  let fail = true;
  function Child() { if (fail) throw new Error('private input should never be reported'); return <Text>Recovered</Text>; }
  const log = jest.spyOn(console, 'error').mockImplementation(() => undefined);
  const report = jest.fn();
  const screen = await render(<CrashBoundary report={report}><Child /></CrashBoundary>);
  expect(screen.getByText('Something went wrong')).toBeTruthy();
  expect(report).toHaveBeenCalledWith({ event: 'mobile_render_crash' });
  expect(JSON.stringify(report.mock.calls)).not.toContain('private input');
  fail = false;
  await fireEvent.press(screen.getByRole('button', { name: 'Try again' }));
  expect(screen.getByText('Recovered')).toBeTruthy();
  log.mockRestore();
});
