/**
 * Shared chat message model (TC-A thread + TC-B stream target).
 *
 * Why: CrafterChat renders the thread, useChatStream appends deltas/toolcalls
 * into it, ToolcallView renders tool blocks from it. One model, three users.
 */

export interface ToolCallBlock {
  kind: 'toolcall';
  id: string;
  name: string;
  /** Args as received; rendering layer redacts secret-looking keys. */
  args: Record<string, unknown>;
  result?: { ok: boolean; summary: string };
  status: 'running' | 'done' | 'error';
}

export interface ReasoningBlock {
  kind: 'reasoning';
  id: string;
  text: string;
}

export type AssistantBlock =
  | { kind: 'text'; id: string; text: string }
  | ToolCallBlock
  | ReasoningBlock;

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  imageUrl?: string;
  imageAlt?: string;
  blocks?: AssistantBlock[];
  pending?: boolean;
  error?: string;
}

let counter = 0;
/** Stable client-side id for message/block keys. */
export function nextId(prefix: string): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter}`;
}

/** Redact secret-looking arg keys before display in ToolcallView. */
export function redactArgs(args: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(args)) {
    out[k] = /key|token|secret|password|auth/i.test(k) ? '[redacted]' : v;
  }
  return out;
}

export interface HistoryRecord {
  role: string;
  text: string;
  at?: number;
}

/**
 * Map persisted history records (GET /api/chat/history) to thread messages.
 * Why (sidebar resume): the thread renders ChatMessage; history rows carry
 * only role/text, so user rows map 1:1 and assistant rows become plain-text
 * messages (no blocks to re-animate).
 */
export function historyToMessages(history: HistoryRecord[]): ChatMessage[] {
  return history.map((h) =>
    h.role === 'assistant'
      ? { id: nextId('hist'), role: 'assistant' as const, text: h.text ?? '' }
      : { id: nextId('hist'), role: 'user' as const, text: h.text ?? '' },
  );
}
