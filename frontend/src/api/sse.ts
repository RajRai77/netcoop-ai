// Fetch-based Server-Sent Events client for GET /api/incidents/{id}/stream.
// - works with Authorization headers (EventSource cannot send them)
// - reconnects with ?after=<last workflow seq> and exponential backoff
// - de-duplicates `attempt` (attempt_id) and `challenge` ((challenge_id, at)) across reconnects
// - stops after the `end` event
import { apiUrl, authHeaders } from './client';

export type StreamEvent =
  | { type: 'workflow'; data: { seq: number; state: string; [k: string]: unknown } }
  | { type: 'attempt'; data: { attempt_id: string; [k: string]: unknown } }
  | { type: 'challenge'; data: { challenge: { challenge_id: string }; outcome: { at: string; outcome: string } } }
  | { type: 'report'; data: { revision: number; status: string } }
  | { type: 'end'; data: { state: string; revision: number | null } };

export interface StreamHandle { close: () => void }

export function openIncidentStream(
  incidentId: string,
  onEvent: (e: StreamEvent) => void,
  onStatus: (s: 'connecting' | 'open' | 'reconnecting' | 'ended' | 'error') => void,
): StreamHandle {
  let lastSeq = 0;
  let closed = false;
  let attempt = 0;
  const seenAttempts = new Set<string>();
  const seenOutcomes = new Set<string>();
  let ctrl: AbortController | null = null;

  const dispatch = (type: string, raw: string) => {
    let data: unknown;
    try {
      data = JSON.parse(raw);
    } catch {
      return;
    }
    if (type === 'workflow') {
      const seq = (data as { seq: number }).seq;
      if (seq <= lastSeq) return;
      lastSeq = seq;
    } else if (type === 'attempt') {
      const id = (data as { attempt_id: string }).attempt_id;
      if (seenAttempts.has(id)) return;
      seenAttempts.add(id);
    } else if (type === 'challenge') {
      const d = data as { challenge: { challenge_id: string }; outcome: { at: string } };
      const key = `${d.challenge.challenge_id}@${d.outcome.at}`;
      if (seenOutcomes.has(key)) return;
      seenOutcomes.add(key);
    }
    onEvent({ type, data } as StreamEvent);
  };

  const run = async () => {
    while (!closed) {
      ctrl = new AbortController();
      onStatus(attempt === 0 ? 'connecting' : 'reconnecting');
      try {
        const res = await fetch(apiUrl(`/api/incidents/${incidentId}/stream?after=${lastSeq}`), {
          headers: { Accept: 'text/event-stream', ...authHeaders() },
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
        onStatus('open');
        attempt = 0;
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        let ended = false;
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let idx: number;
          while ((idx = buf.indexOf('\n\n')) >= 0) {
            const block = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            let ev = 'message';
            const dataLines: string[] = [];
            for (const line of block.split('\n')) {
              if (line.startsWith('event:')) ev = line.slice(6).trim();
              else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
            }
            if (!dataLines.length) continue; // comment / keep-alive
            dispatch(ev, dataLines.join('\n'));
            if (ev === 'end') ended = true;
          }
        }
        if (ended) {
          onStatus('ended');
          return;
        }
      } catch (e) {
        if (closed || (e instanceof DOMException && e.name === 'AbortError')) return;
        onStatus('error');
      }
      attempt += 1;
      await new Promise((r) => setTimeout(r, Math.min(15000, 500 * 2 ** attempt)));
    }
  };
  void run();
  return {
    close: () => {
      closed = true;
      ctrl?.abort();
    },
  };
}
