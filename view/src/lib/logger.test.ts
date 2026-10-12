/**
 * Logger redaction tests (TC-A-01 §1.5 / TC-B-02 §1.5).
 * Keys, prompts, message content, image data must never reach logs.
 */
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { clearViewLogs, getViewLogs, logger, redact } from './logger';

beforeEach(() => {
  clearViewLogs();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('redact', () => {
  it('redacts sensitive keys', () => {
    const out = redact({ api_key: 'sk-secret-123', label: 'mine', token: 'abc', prompt: 'hello' });
    expect(out.api_key).toBe('[redacted]');
    expect(out.token).toBe('[redacted]');
    expect(out.prompt).toBe('[redacted]');
    expect(out.label).toBe('mine');
  });

  it('redacts nested sensitive keys and long blobs', () => {
    const blob = 'a'.repeat(200);
    const out = redact({ nested: { password: 'pw', ok: true }, note: blob, image: blob });
    expect((out.nested as Record<string, unknown>).password).toBe('[redacted]');
    expect((out.nested as Record<string, unknown>).ok).toBe(true);
    expect(out.note).toBe('[truncated]');
    // sensitive key wins over length: image data never leaks in any form
    expect(out.image).toBe('[redacted]');
  });

  it('flags long base64-ish image data', () => {
    const b64 = 'iVBORw0KGgo'.repeat(10); // 110 chars, base64 alphabet
    const out = redact({ dataUrl: `data:image/png;base64,${b64}` });
    // key "dataUrl" matches sensitive pattern → redacted wholesale
    expect(out.dataUrl).toBe('[redacted]');
  });
});

describe('logger', () => {
  it('never emits raw keys/prompts through console', () => {
    const spy = vi.spyOn(console, 'info').mockImplementation(() => {});
    logger.info('settings.profile.tested', { api_key: 'sk-live-xyz', message: 'hello world' });
    expect(spy).toHaveBeenCalledOnce();
    const line = String(spy.mock.calls[0]?.[0] ?? '');
    expect(line).not.toContain('sk-live-xyz');
    expect(line).toContain('[redacted]');
  });
});

describe('view log ring buffer', () => {
  it('records redacted entries via getViewLogs', () => {
    vi.spyOn(console, 'info').mockImplementation(() => {});
    logger.info('chat.stream.started', { api_key: 'sk-live-xyz', session_id: 's1' });
    const logs = getViewLogs();
    expect(logs).toHaveLength(1);
    expect(logs[0]).toMatchObject({ level: 'info', event: 'chat.stream.started' });
    expect(logs[0]!.fields.api_key).toBe('[redacted]');
    expect(JSON.stringify(logs)).not.toContain('sk-live-xyz');
  });

  it('is bounded at 200 records', () => {
    vi.spyOn(console, 'debug').mockImplementation(() => {});
    for (let i = 0; i < 250; i++) logger.debug('tick', { i });
    const logs = getViewLogs();
    expect(logs).toHaveLength(200);
    expect(logs[0]!.fields.i).toBe(50);
  });

  it('clearViewLogs empties the buffer', () => {
    vi.spyOn(console, 'info').mockImplementation(() => {});
    logger.info('something', {});
    expect(getViewLogs()).toHaveLength(1);
    clearViewLogs();
    expect(getViewLogs()).toHaveLength(0);
  });
});
