import { fetch } from 'expo/fetch';
import { streamSummary } from '../src/features/discovery/summary-api';
import { summaryStream } from './summary-stream';

beforeEach(() => jest.mocked(fetch).mockReset());

test('SSE parsing survives byte boundaries, CRLF and multi-byte text', async () => {
  const raw = 'event: summary\r\ndata: {"text":"café"}\r\n\r\nevent: done\ndata: {"grounded":true,"results":1,"summary_id":"opaque-id"}\n\n';
  const bytes = new TextEncoder().encode(raw);
  let index = 0;
  const reader = { read: async () => ({ done: false, value: bytes.slice(index, ++index) }), cancel: jest.fn(async () => {}), releaseLock: jest.fn() };
  jest.mocked(fetch).mockResolvedValue({ ok: true, headers: { get: () => 'text/event-stream' }, body: { getReader: () => reader } } as never);
  const text = jest.fn();
  await expect(streamSummary(['owner/repo'], 'session', new AbortController().signal, text)).resolves.toEqual({ text: 'café', summaryId: 'opaque-id' });
  expect(text).toHaveBeenCalledWith('café');
  expect(jest.mocked(fetch).mock.calls[0][1]!.headers).toEqual({ Authorization: 'Bearer session', 'Content-Type': 'application/json', Accept: 'text/event-stream' });
});

test.each(['invalid JSON', 'unknown event', 'invalid text', 'ungrounded', 'empty', 'EOF', 'bytes', 'text'])('%s refuses a completed summary', async failure => {
  const stream = summaryStream();
  jest.mocked(fetch).mockResolvedValue(stream.response as never);
  const promise = streamSummary(['owner/repo'], 'session', new AbortController().signal, () => {});
  const assertion = expect(promise).rejects.toThrow();
  await Promise.resolve();
  if (failure === 'EOF') stream.end();
  else if (failure === 'bytes') stream.raw('x'.repeat(32769));
  else if (failure === 'text') stream.event('summary', { text: 'x'.repeat(8001) });
  else if (failure === 'invalid JSON') stream.raw('event: summary\ndata: !\n\n');
  else if (failure === 'unknown event') stream.event('error', {});
  else if (failure === 'invalid text') stream.event('summary', { text: 4 });
  else stream.event('done', { grounded: failure === 'empty', reason: 'ungrounded' });
  await assertion;
  expect(stream.reader.cancel).toHaveBeenCalled();
});

test.each([
  { ok: false },
  { ok: true, headers: { get: () => 'application/json' } },
  { ok: true, headers: { get: () => 'text/event-stream' }, body: null },
])('invalid HTTP response refuses the summary', async response => {
  jest.mocked(fetch).mockResolvedValue(response as never);
  await expect(streamSummary(['owner/repo'], 'session', new AbortController().signal, () => {})).rejects.toThrow();
});
