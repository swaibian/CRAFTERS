/**
 * Tiny view-layer logger with redaction (TC-A-01 §1.5, TC-B-02 §1.5).
 *
 * Why: chat/file-flow/stream/settings boundaries need observable diagnostics,
 * but prompts, document content, image data, API keys and message content must
 * never reach logs. Every value passes through {@link redact} before output.
 *
 * Contract: `debug/info/warn/error(event, fields?)` — event is a short stable
 * code (e.g. "chat.stream.started"); fields is a flat record of safe scalars.
 * Sensitive keys (key, token, secret, prompt, message, content, image, data,
 * base64, authorization) are replaced with "[redacted]"; long strings are
 * truncated to 120 chars. No `console.*` calls exist elsewhere in src/.
 */

const SENSITIVE_KEY_PATTERN =
  /key|token|secret|password|prompt|message|content|image|data|base64|authorization|bearer/i;

const MAX_VALUE_LENGTH = 120;

function redactValue(value: unknown): unknown {
  if (typeof value === 'string') {
    if (value.length > MAX_VALUE_LENGTH) return '[truncated]';
    // Long base64-ish blobs (image data) are never logged in full.
    if (value.length > 64 && /^[A-Za-z0-9+/=_-]+$/.test(value)) return '[redacted-blob]';
    return value;
  }
  if (Array.isArray(value)) return value.map(redactValue);
  if (value !== null && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = SENSITIVE_KEY_PATTERN.test(k) ? '[redacted]' : redactValue(v);
    }
    return out;
  }
  return value;
}

/** Redact a fields record for safe logging. Exported for tests. */
export function redact(fields: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!fields) return {};
  return redactValue(fields) as Record<string, unknown>;
}

type Level = 'debug' | 'info' | 'warn' | 'error';

export interface ViewLogRecord {
  at: string;
  level: Level;
  event: string;
  fields: Record<string, unknown>;
}

const RING_CAPACITY = 200;
const ring: ViewLogRecord[] = [];

/**
 * In-memory ring buffer of the last 200 redacted log records.
 * Why (diagnostics page): the log viewer shows recent view activity without
 * touching the network. Records are redacted at emit time, so secrets/keys
 * never sit in the buffer.
 */
export function getViewLogs(): ViewLogRecord[] {
  return [...ring];
}

/** Clear the in-memory log buffer (Diagnostics page Clear button). */
export function clearViewLogs(): void {
  ring.length = 0;
}

function emit(level: Level, event: string, fields?: Record<string, unknown>): void {
  const safe = redact(fields);
  ring.push({ at: new Date().toISOString(), level, event, fields: safe });
  if (ring.length > RING_CAPACITY) ring.splice(0, ring.length - RING_CAPACITY);
  const line = `[crafter:${level}] ${event} ${JSON.stringify(safe)}`;
  if (level === 'error') console.error(line);
  else if (level === 'warn') console.warn(line);
  else if (level === 'info') console.info(line);
  else console.debug(line);
}

export const logger = {
  debug: (event: string, fields?: Record<string, unknown>) => emit('debug', event, fields),
  info: (event: string, fields?: Record<string, unknown>) => emit('info', event, fields),
  warn: (event: string, fields?: Record<string, unknown>) => emit('warn', event, fields),
  error: (event: string, fields?: Record<string, unknown>) => emit('error', event, fields),
};
