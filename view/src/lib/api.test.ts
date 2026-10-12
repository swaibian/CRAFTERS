/**
 * API client tests: SSE payload parsing, URL builders, graceful degradation
 * when the controller is down (fetch rejecting → ApiError unreachable).
 */
import { describe, expect, it, vi, afterEach } from 'vitest';
import {
  ApiError,
  deleteConversation,
  downloadResultUrl,
  fetchConversations,
  fetchDiagnostics,
  fetchOpenedFile,
  fetchProfileModels,
  fetchTeams,
  loadHistory,
  openFile,
  parseStreamPayload,
  streamChat,
  testScaicoKey,
  thumbnailUrl,
  type StreamEvent,
} from './api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('parseStreamPayload', () => {
  it('parses each send_task_stream event', () => {
    expect(parseStreamPayload(JSON.stringify({ event: 'response.started', run_id: 'r1', model: 'm1', team: 't1' }))).toEqual({
      type: 'response.started',
      run_id: 'r1',
      model: 'm1',
      team: 't1',
    });
    // team may be null; model may be absent on older controllers
    expect(parseStreamPayload(JSON.stringify({ event: 'response.started', run_id: 'r1', team: null }))).toEqual({
      type: 'response.started',
      run_id: 'r1',
      model: '',
      team: null,
    });
    expect(parseStreamPayload(JSON.stringify({ event: 'text.delta', delta: 'hi' }))).toEqual({
      type: 'text.delta',
      delta: 'hi',
    });
    expect(parseStreamPayload(JSON.stringify({ event: 'text.delta', delta: 'plan', phase: 'reasoning' }))).toEqual({
      type: 'text.delta',
      delta: 'plan',
      phase: 'reasoning',
    });
    expect(
      parseStreamPayload(JSON.stringify({ event: 'tool.call', name: 'craft_look', args: { a: 1 } })),
    ).toEqual({ type: 'tool.call', name: 'craft_look', args: { a: 1 } });
    expect(
      parseStreamPayload(JSON.stringify({ event: 'tool.result', name: 'craft_look', ok: true, summary: 's' })),
    ).toEqual({ type: 'tool.result', name: 'craft_look', ok: true, summary: 's' });
    expect(parseStreamPayload(JSON.stringify({ event: 'response.completed', message_id: 'm1' }))).toEqual({
      type: 'response.completed',
      message_id: 'm1',
    });
    expect(parseStreamPayload(JSON.stringify({ event: 'response.error', message: 'boom' }))).toEqual({
      type: 'response.error',
      message: 'boom',
    });
  });

  it('ignores unknown events and malformed JSON', () => {
    expect(parseStreamPayload(JSON.stringify({ event: 'nope' }))).toBeNull();
    expect(parseStreamPayload('not json{{{')).toBeNull();
  });

  it('prefers the SSE event line over inline JSON event fields', () => {
    expect(
      parseStreamPayload(JSON.stringify({ type: 'text.delta', delta: 'ignored', name: 'command_run' }), 'tool.call'),
    ).toEqual({ type: 'tool.call', name: 'command_run', args: {} });
  });
});

describe('SSE wire format', () => {
  function stubSseStream(chunks: string[]) {
    const encoder = new TextEncoder();
    let i = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        body: {
          getReader: () => ({
            read: async () =>
              i < chunks.length
                ? { done: false, value: encoder.encode(chunks[i++]) }
                : { done: true, value: undefined },
            releaseLock: () => {},
          }),
        },
      }),
    );
  }

  function collectStream(chunks: string[]): Promise<StreamEvent[]> {
    stubSseStream(chunks);
    return new Promise((resolve, reject) => {
      const events: StreamEvent[] = [];
      streamChat(
        { session_id: 's1', message: 'hi' },
        {
          onEvent: (e) => events.push(e),
          onDone: () => resolve(events),
          onError: (err) => reject(err),
        },
      );
    });
  }

  it('routes a classic event:/data: frame', async () => {
    await expect(collectStream(['event: tool.call\ndata: {"name":"command_run"}\n\n'])).resolves.toEqual([
      { type: 'tool.call', name: 'command_run', args: {} },
    ]);
  });

  it('falls back to the inline event field on bare data frames', async () => {
    await expect(
      collectStream(['data: {"event":"text.delta","delta":"hi"}\n\ndata: {"type":"response.completed","message_id":"m1"}\n\n']),
    ).resolves.toEqual([
      { type: 'text.delta', delta: 'hi' },
      { type: 'response.completed', message_id: 'm1' },
    ]);
  });

  it('routes mixed chunks where event line and data share or split chunk strings', async () => {
    await expect(
      collectStream([
        'event: text.delta\ndata: {"delta":"a"}\n\nevent: tool.call\ndata: {"name":"command_run"}\n\n',
        'event: response.completed\ndata: {"message_id":"m1"}\n\n',
        'event: text.delta\n',
        'data: {"delta":"b"}\n\n',
      ]),
    ).resolves.toEqual([
      { type: 'text.delta', delta: 'a' },
      { type: 'tool.call', name: 'command_run', args: {} },
      { type: 'response.completed', message_id: 'm1' },
      { type: 'text.delta', delta: 'b' },
    ]);
  });
});

describe('URL builders', () => {
  it('builds thumbnail and download URLs on the controller routes', () => {
    expect(thumbnailUrl('doc 1')).toBe('/api/files/doc%201/thumbnail');
    expect(thumbnailUrl('doc 1', 's1')).toBe('/api/files/doc%201/thumbnail?session_id=s1');
    expect(downloadResultUrl('doc 1')).toBe('/api/files/doc%201/download');
    expect(downloadResultUrl('doc 1', 's1')).toBe('/api/files/doc%201/download?session_id=s1');
  });
});

describe('controller-shape compat (Lane 4)', () => {
  it('parseStreamPayload accepts the controller SSE payloads', async () => {
    const mod = await import('./api');
    // tool.call carries call_id + arguments server-side
    expect(
      mod.parseStreamPayload(JSON.stringify({ event: 'tool.call', name: 'photo.transform', call_id: 'c1', arguments: { kind: 'resize' } })),
    ).toEqual({ type: 'tool.call', name: 'photo.transform', args: { kind: 'resize' } });
    // tool.result carries error + summary server-side
    expect(
      mod.parseStreamPayload(JSON.stringify({ event: 'tool.result', name: 'photo.transform', ok: true, error: '', summary: 'photo.transform ok (revision 2)' })),
    ).toEqual({ type: 'tool.result', name: 'photo.transform', ok: true, summary: 'photo.transform ok (revision 2)' });
    expect(
      mod.parseStreamPayload(JSON.stringify({ event: 'tool.result', name: 'photo.transform', ok: false, error: 'nope' })),
    ).toEqual({ type: 'tool.result', name: 'photo.transform', ok: false, summary: 'nope' });
    // response.completed carries run_id + records + message_id server-side
    expect(
      mod.parseStreamPayload(JSON.stringify({ event: 'response.completed', run_id: 'run_1', records: ['rec_a'], message_id: 'run_1' })),
    ).toEqual({ type: 'response.completed', message_id: 'run_1' });
  });

  it('fetchProfiles merges active_profile_id from the inline field', async () => {
    const mod = await import('./api');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ profiles: [{ id: 'p1' }], active_profile_id: 'p1' }),
      }),
    );
    await expect(mod.fetchProfiles()).resolves.toEqual({ profiles: [{ id: 'p1' }], active_profile_id: 'p1' });
  });

  it('fetchProfiles falls back to /api/settings/active when inline is absent', async () => {
    const mod = await import('./api');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (url: string) => {
        if (String(url).includes('/api/settings/active'))
          return { ok: true, json: async () => ({ active_profile_id: 'p9' }) };
        return { ok: true, json: async () => ({ profiles: [] }) };
      }),
    );
    await expect(mod.fetchProfiles()).resolves.toEqual({ profiles: [], active_profile_id: 'p9' });
  });

  it('createProfile unwraps the controller {profile} envelope', async () => {
    const mod = await import('./api');
    const bare = { id: 'p1', label: 'A', api_base: 'http://x', api_key_masked: '…1', default_model: 'm' };
    const spy = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ profile: bare }) });
    vi.stubGlobal('fetch', spy);
    await expect(
      mod.createProfile({ label: 'A', api_base: 'http://x', api_key: 'k', default_model: 'm' }),
    ).resolves.toEqual(bare);
  });

  it('testProfileConnection normalizes the controller {ok, error} shape', async () => {
    const mod = await import('./api');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: false, error: 'endpoint unreachable' }) }),
    );
    await expect(mod.testProfileConnection({ label: 'a', api_base: 'http://x', api_key: '', default_model: '' })).resolves.toEqual({
      ok: false,
      message: 'endpoint unreachable',
    });
  });

  it('openFile maps the controller {kind, source_name} shape to the view', async () => {
    const mod = await import('./api');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ doc_id: 'd1', kind: 'photo', source_name: 'a.png', inspect: { width: 8 } }),
      }),
    );
    const opened = await mod.openFile(new File(['x'], 'a.png'), 'photocraft', 's9');
    expect(opened).toMatchObject({ doc_id: 'd1', app: 'photo', name: 'a.png', session_id: 's9' });
    expect(opened.thumbnail_url).toContain('/api/files/d1/thumbnail?session_id=s9');
  });
});

describe('graceful degradation', () => {
  it('fetchTeams surfaces unreachable ApiError when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(fetchTeams()).rejects.toMatchObject({ unreachable: true } as Partial<ApiError>);
  });

  it('fetchTeams throws status ApiError on HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    await expect(fetchTeams()).rejects.toMatchObject({ status: 500 } as Partial<ApiError>);
  });
});

describe('model picker contract', () => {
  it('fetchProfileModels returns ids + cached flag', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ models: [{ id: 'm1' }, { id: 'm2' }], cached: true }),
      }),
    );
    await expect(fetchProfileModels('p1')).resolves.toEqual({
      models: [{ id: 'm1' }, { id: 'm2' }],
      cached: true,
    });
    const [[url]] = (fetch as unknown as { mock: { calls: [string][] } }).mock.calls;
    expect(url).toContain('/api/settings/profiles/models?profile_id=p1');
  });

  it('fetchProfileModels surfaces 404 for unknown profiles', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    await expect(fetchProfileModels('nope')).rejects.toMatchObject({ status: 404 } as Partial<ApiError>);
  });
});

describe('diagnostics contract', () => {
  it('fetchDiagnostics returns checks + recent', async () => {
    const payload = {
      checks: {
        gateway: { ok: true, latency_ms: 3 },
        controller: { ok: true },
        scaico: { ok: false, configured: false },
        litellm: { ok: true, configured: true, model: 'm' },
      },
      recent: [{ at: '2026-01-01T00:00:00Z', service: 'gateway', ok: true }],
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => payload }));
    await expect(fetchDiagnostics()).resolves.toEqual(payload);
  });

  it('testScaicoKey posts an empty body when no key is given (stored key)', async () => {
    const spy = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, latency_ms: 12 }) });
    vi.stubGlobal('fetch', spy);
    await expect(testScaicoKey()).resolves.toEqual({ ok: true, latency_ms: 12 });
    expect(spy).toHaveBeenCalledWith('/api/settings/scaico-key/test', expect.objectContaining({ method: 'POST' }));
    expect(JSON.parse(String(spy.mock.calls[0]?.[1]?.body ?? '{}'))).toEqual({});
  });

  it('testScaicoKey forwards an explicit key', async () => {
    const spy = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal('fetch', spy);
    await testScaicoKey('scaico-x');
    expect(JSON.parse(String(spy.mock.calls[0]?.[1]?.body ?? '{}'))).toEqual({ api_key: 'scaico-x' });
  });
});

describe('conversations contract', () => {
  it('fetchConversations returns the list newest-first', async () => {
    const payload = {
      conversations: [
        { id: 'c2', app: 'photocraft', title: 'B', updated_at: '2026-01-02T00:00:00Z', message_count: 3, doc_ids: ['d1'] },
        { id: 'c1', app: 'gridcraft', title: 'A', updated_at: '2026-01-01T00:00:00Z', message_count: 1, doc_ids: [] },
      ],
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => payload }));
    await expect(fetchConversations()).resolves.toEqual(payload.conversations);
  });

  it('deleteConversation issues DELETE and returns the deleted id', async () => {
    const spy = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ deleted: 'c1' }) });
    vi.stubGlobal('fetch', spy);
    await expect(deleteConversation('c1')).resolves.toEqual({ deleted: 'c1' });
    expect(spy).toHaveBeenCalledWith('/api/conversations/c1', expect.objectContaining({ method: 'DELETE' }));
  });

  it('loadHistory returns messages for the session', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ messages: [{ role: 'user', text: 'hi' }] }) }),
    );
    await expect(loadHistory('s1')).resolves.toEqual([{ role: 'user', text: 'hi' }]);
  });

  it('fetchOpenedFile rebinds a doc into a session', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ doc_id: 'd1', app: 'photocraft', name: 'a.png', session_id: 's1', inspect: {} }),
      }),
    );
    const opened = await fetchOpenedFile('d1', 's1');
    expect(opened).toMatchObject({ doc_id: 'd1', session_id: 's1' });
    const [[url]] = (fetch as unknown as { mock: { calls: [string][] } }).mock.calls;
    expect(url).toContain('/api/files/d1?session_id=s1');
  });

  it('openFile sends session_id as a form field when provided', async () => {
    const spy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ doc_id: 'd1', app: 'photocraft', name: 'a.png', session_id: 's9', inspect: {} }),
    });
    vi.stubGlobal('fetch', spy);
    await openFile(new File(['x'], 'a.png'), 'photocraft', 's9');
    const form = spy.mock.calls[0]?.[1]?.body as FormData;
    expect(form.get('session_id')).toBe('s9');
  });

  it('openFile stays backward compatible without a session', async () => {
    const spy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ doc_id: 'd1', app: 'photocraft', name: 'a.png', session_id: 'default', inspect: {} }),
    });
    vi.stubGlobal('fetch', spy);
    await openFile(new File(['x'], 'a.png'), 'photocraft');
    const form = spy.mock.calls[0]?.[1]?.body as FormData;
    expect(form.get('session_id')).toBeNull();
  });
});
