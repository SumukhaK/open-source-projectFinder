export function summaryStream() {
  let resolve: (value: { done: boolean; value?: Uint8Array }) => void = () => {};
  let reject: (reason: Error) => void = () => {};
  const read = jest.fn(() => new Promise<{ done: boolean; value?: Uint8Array }>((yes, no) => { resolve = yes; reject = no; }));
  const reader = { read, cancel: jest.fn(async () => {}), releaseLock: jest.fn() };
  return {
    response: { ok: true, headers: { get: () => 'text/event-stream' }, body: { getReader: () => reader } },
    reader,
    event: (name: string, data: unknown) => resolve({ done: false, value: new TextEncoder().encode(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`) }),
    raw: (text: string) => resolve({ done: false, value: new TextEncoder().encode(text) }),
    end: () => resolve({ done: true }),
    fail: () => reject(new Error('network')),
  };
}
