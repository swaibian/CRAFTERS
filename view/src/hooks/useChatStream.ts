/**
 * SSE streaming hook (TC-B-01).
 *
 * Why (SW-REQ-STREAM): subscribes to POST /api/chat/stream, assembles
 * `text.delta` chunks into the pending assistant message, routes
 * `tool.call`/`tool.result` into ToolcallView blocks, surfaces
 * `response.error` inline. Reduced-motion: disables animated auto-scroll.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, streamChat, type ChatStreamRequest } from '../lib/api';
import { nextId, type AssistantBlock, type ChatMessage } from '../lib/chat';
import { logger } from '../lib/logger';

export interface StreamState {
  streaming: boolean;
  runId: string | null;
  /** Answering model from response.started (null until the run starts). */
  model: string | null;
  error: string | null;
  cancel: () => void;
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true,
  );
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mq) return;
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

export function useChatStream(
  appendMessage: (m: ChatMessage) => void,
  patchMessage: (id: string, patch: (m: ChatMessage) => ChatMessage) => void,
): StreamState & { send: (req: ChatStreamRequest, userText: string, imageUrl?: string) => void } {
  const [streaming, setStreaming] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<() => void>(() => {});

  const cancel = useCallback(() => {
    cancelRef.current();
    setStreaming(false);
  }, []);

  const send = useCallback(
    (req: ChatStreamRequest, userText: string, imageUrl?: string) => {
      const assistantId = nextId('asst');
      appendMessage({
        id: nextId('user'),
        role: 'user',
        text: userText,
        imageUrl,
        imageAlt: imageUrl ? 'Image attached to chat message' : undefined,
      });
      appendMessage({ id: assistantId, role: 'assistant', text: '', blocks: [], pending: true });
      setStreaming(true);
      setError(null);
      setModel(null);

      let textBlockId: string | null = null;
      let toolSeq = 0;

      const stop = streamChat(req, {
        onEvent: (event) => {
          switch (event.type) {
            case 'response.started':
              setRunId(event.run_id);
              setModel(event.model || null);
              break;
            case 'text.delta':
              patchMessage(assistantId, (m) => {
                const blocks: AssistantBlock[] = m.blocks ?? [];
                const last = blocks[blocks.length - 1];
                const kind = event.phase === 'reasoning' ? 'reasoning' : event.phase === 'final' ? 'final' : 'text';
                if (last && last.kind === kind && last.id === textBlockId) {
                  return {
                    ...m,
                    blocks: [...blocks.slice(0, -1), { ...last, text: last.text + event.delta }],
                  };
                }
                const id = nextId('txt');
                textBlockId = id;
                const nextBlock: AssistantBlock =
                  kind === 'reasoning'
                    ? { kind: 'reasoning', id, text: event.delta }
                    : kind === 'final'
                      ? { kind: 'final', id, text: event.delta }
                      : { kind: 'text', id, text: event.delta };
                return { ...m, blocks: [...blocks, nextBlock] };
              });
              break;
            case 'tool.call':
              toolSeq += 1;
              patchMessage(assistantId, (m) => ({
                ...m,
                blocks: [
                  ...(m.blocks ?? []),
                  {
                    kind: 'toolcall',
                    id: `tool-${toolSeq}`,
                    name: event.name,
                    args: event.args,
                    status: 'running' as const,
                  },
                ],
              }));
              break;
            case 'tool.result':
              patchMessage(assistantId, (m) => ({
                ...m,
                blocks: (m.blocks ?? []).map((b) =>
                  b.kind === 'toolcall' && b.name === event.name && b.status === 'running'
                    ? { ...b, result: { ok: event.ok, summary: event.summary }, status: event.ok ? ('done' as const) : ('error' as const) }
                    : b,
                ),
              }));
              break;
            case 'response.completed':
              patchMessage(assistantId, (m) => ({ ...m, pending: false }));
              setStreaming(false);
              logger.info('chat.stream.completed', { session_id: req.session_id });
              break;
            case 'response.error':
              patchMessage(assistantId, (m) => ({ ...m, pending: false, error: event.message }));
              setStreaming(false);
              setError(event.message);
              logger.warn('chat.stream.error', {});
              break;
          }
        },
        onDone: () => {
          patchMessage(assistantId, (m) => (m.pending ? { ...m, pending: false } : m));
          setStreaming(false);
        },
        onError: (err: ApiError) => {
          const msg = err.unreachable
            ? 'Controller unreachable — showing mock fallback. Start the controller (:8790) and retry.'
            : err.message;
          patchMessage(assistantId, (m) => ({ ...m, pending: false, error: msg }));
          setStreaming(false);
          setError(msg);
        },
      });
      cancelRef.current = stop;
    },
    [appendMessage, patchMessage],
  );

  return { streaming, runId, model, error, cancel, send };
}
