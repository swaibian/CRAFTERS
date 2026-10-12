/**
 * Stream-hook tests (TC-B-01): chunk assembly, toolcall routing, error and
 * unreachable-controller paths — with a mocked SSE reader.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { useChatStream } from '../hooks/useChatStream';
import type { ChatMessage } from '../lib/chat';

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
  return { ok: true, status: 200, body: stream } as unknown as Response;
}

function sseData(payload: unknown): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useChatStream', () => {
  it('assembles text deltas and toolcall blocks from a mocked stream', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          sseData({ event: 'response.started', run_id: 'r1' }),
          sseData({ event: 'text.delta', delta: 'Hello ' }),
          sseData({ event: 'text.delta', delta: 'world' }),
          sseData({ event: 'tool.call', name: 'craft_look', args: {} }),
          sseData({ event: 'tool.result', name: 'craft_look', ok: true, summary: 'seen' }),
          sseData({ event: 'response.completed', message_id: 'm1' }),
        ]),
      ),
    );
    const messages: ChatMessage[] = [];
    const appendMessage = (m: ChatMessage) => {
      messages.push(m);
    };
    const patchMessage = (id: string, patch: (m: ChatMessage) => ChatMessage) => {
      const i = messages.findIndex((m) => m.id === id);
      if (i >= 0) messages[i] = patch(messages[i]!);
    };
    const { result } = renderHook(() => useChatStream(appendMessage, patchMessage));
    await act(async () => {
      result.current.send({ session_id: 's1', message: 'hi' }, 'hi');
      await new Promise((r) => setTimeout(r, 50));
    });
    const asst = messages.find((m) => m.role === 'assistant');
    expect(asst).toBeDefined();
    const text = (asst!.blocks ?? []).filter((b) => b.kind === 'text');
    expect(text.map((b) => (b as { text: string }).text).join('')).toBe('Hello world');
    const tool = (asst!.blocks ?? []).find((b) => b.kind === 'toolcall');
    expect(tool).toMatchObject({ name: 'craft_look', status: 'done' });
    expect(asst!.pending).toBe(false);
  });

  it('keeps intermediate reasoning separate from the final response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          sseData({ event: 'text.delta', delta: 'Planning change.\n', phase: 'reasoning' }),
          sseData({ event: 'tool.call', name: 'photo_transform', args: {} }),
          sseData({ event: 'tool.result', name: 'photo_transform', ok: true, summary: 'done' }),
          sseData({ event: 'text.delta', delta: '[observed revision 1]', phase: 'reasoning' }),
          sseData({ event: 'text.delta', delta: 'Rotated the image.', phase: 'final' }),
          sseData({ event: 'response.completed', message_id: 'm2' }),
        ]),
      ),
    );
    const messages: ChatMessage[] = [];
    const { result } = renderHook(() =>
      useChatStream(
        (message) => messages.push(message),
        (id, patch) => {
          const index = messages.findIndex((message) => message.id === id);
          if (index >= 0) messages[index] = patch(messages[index]!);
        },
      ),
    );
    await act(async () => {
      result.current.send({ session_id: 's1', message: 'rotate' }, 'rotate');
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    const assistant = messages.find((message) => message.role === 'assistant');
    expect(assistant?.blocks?.filter((block) => block.kind === 'reasoning').map((block) => block.text)).toEqual([
      'Planning change.\n',
      '[observed revision 1]',
    ]);
    expect(assistant?.blocks?.find((block) => block.kind === 'final')).toMatchObject({
      text: 'Rotated the image.',
    });
  });

  it('exposes the answering model from response.started', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          sseData({ event: 'response.started', run_id: 'r9', model: 'm-live', team: null }),
          sseData({ event: 'response.completed', message_id: 'm1' }),
        ]),
      ),
    );
    const messages: ChatMessage[] = [];
    const appendMessage = (m: ChatMessage) => {
      messages.push(m);
    };
    const patchMessage = (id: string, patch: (m: ChatMessage) => ChatMessage) => {
      const i = messages.findIndex((m) => m.id === id);
      if (i >= 0) messages[i] = patch(messages[i]!);
    };
    const { result } = renderHook(() => useChatStream(appendMessage, patchMessage));
    await act(async () => {
      result.current.send({ session_id: 's1', message: 'hi', model: 'm-live' }, 'hi');
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(result.current.model).toBe('m-live');
    // The selected model flows into the stream request body.
    const [[, init]] = (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls;
    expect(JSON.parse(String(init?.body))).toMatchObject({ model: 'm-live' });
  });

  it('surfaces response.error inline', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(sseResponse([sseData({ event: 'response.error', message: 'bad model' })])),
    );
    const messages: ChatMessage[] = [];
    const { result } = renderHook(() =>
      useChatStream(
        (m) => messages.push(m),
        (id, patch) => {
          const i = messages.findIndex((m) => m.id === id);
          if (i >= 0) messages[i] = patch(messages[i]!);
        },
      ),
    );
    await act(async () => {
      result.current.send({ session_id: 's1', message: 'hi' }, 'hi');
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(messages.find((m) => m.role === 'assistant')?.error).toBe('bad model');
  });

  it('degrades gracefully when the controller is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('down')));
    const messages: ChatMessage[] = [];
    const { result } = renderHook(() =>
      useChatStream(
        (m) => messages.push(m),
        (id, patch) => {
          const i = messages.findIndex((m) => m.id === id);
          if (i >= 0) messages[i] = patch(messages[i]!);
        },
      ),
    );
    await act(async () => {
      result.current.send({ session_id: 's1', message: 'hi' }, 'hi');
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(messages.find((m) => m.role === 'assistant')?.error).toMatch(/mock fallback/i);
  });
});
