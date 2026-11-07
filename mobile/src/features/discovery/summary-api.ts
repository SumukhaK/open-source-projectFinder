import { fetch } from 'expo/fetch';
import { discoveryConfig } from '../../config/discovery';

export async function streamSummary(names: string[], token: string, signal: AbortSignal, onText: (text: string) => void): Promise<{ text: string; summaryId: string | null }> {
  const response = await fetch(`${discoveryConfig.apiUrl}/v1/projects/search/summary`, {
    method: 'POST', signal,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ full_names: names.slice(0, 10) }),
  });
  if (!response.ok || !response.headers.get('content-type')?.startsWith('text/event-stream') || !response.body) throw new Error('No summary');
  const reader = response.body.getReader();
  const cancel = () => { void reader.cancel().catch(() => {}); };
  signal.addEventListener('abort', cancel);
  let buffer = '', text = '', bytes = 0;
  const decoder = new TextDecoder();
  try {
    while (!signal.aborted) {
      const chunk = await reader.read();
      if (signal.aborted || chunk.done) break;
      bytes += chunk.value.byteLength;
      if (bytes > discoveryConfig.summaryMaxBytes) throw new Error('Summary too large');
      buffer += decoder.decode(chunk.value, { stream: true });
      let boundary: RegExpExecArray | null;
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        const lines = frame.split(/\r?\n/);
        const event = lines.find(line => line.startsWith('event:'))?.slice(6).trim();
        const data = JSON.parse(lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n'));
        if (event === 'summary' && typeof data?.text === 'string') {
          text += data.text;
          if (text.length > discoveryConfig.summaryMaxChars) throw new Error('Summary too large');
          onText(text);
        } else if (event === 'done' && data?.grounded === true && text.trim()) {
          return { text, summaryId: typeof data.summary_id === 'string' && data.summary_id.trim() ? data.summary_id : null };
        } else throw new Error('No grounded summary');
      }
    }
    throw new Error('Incomplete summary');
  } finally {
    signal.removeEventListener('abort', cancel);
    cancel();
    reader.releaseLock();
  }
}
