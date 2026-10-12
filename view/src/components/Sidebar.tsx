/**
 * Sidebar: New chat + resume grouped by app.
 *
 * Why: conversations persist server-side; the sidebar lists them newest-first
 * grouped by app (photocraft/gridcraft/pdfcraft/other-unknown) with title,
 * relative time, message count and doc badge. "New chat" clears the opened
 * file + thread and mints a fresh session id. Click resumes: sets the session
 * id, reloads history into the thread, rebinds the opened file via
 * GET /api/files/{doc_id} when doc_ids are present. Delete uses an inline
 * confirm (two-click), never window.confirm.
 */

import { useEffect, useState } from 'react';
import {
  deleteConversation,
  fetchConversations,
  fetchOpenedFile,
  loadHistory,
  type ConversationSummary,
  type OpenedFile,
} from '../lib/api';
import { historyToMessages, type ChatMessage } from '../lib/chat';
import { logger } from '../lib/logger';

export const KNOWN_APPS = ['photocraft', 'gridcraft', 'pdfcraft'] as const;

export function groupLabel(app: string | undefined): string {
  if (app === 'photocraft') return 'photocraft';
  if (app === 'gridcraft') return 'gridcraft';
  if (app === 'pdfcraft') return 'pdfcraft';
  return 'other-unknown';
}

export function groupConversations(convs: ConversationSummary[]): Map<string, ConversationSummary[]> {
  const groups = new Map<string, ConversationSummary[]>();
  for (const c of convs) {
    const label = groupLabel(c.app);
    const list = groups.get(label) ?? [];
    list.push(c);
    groups.set(label, list);
  }
  // Known apps first, then other-unknown.
  const ordered = new Map<string, ConversationSummary[]>();
  for (const app of [...KNOWN_APPS, 'other-unknown']) {
    const list = groups.get(app);
    if (list) ordered.set(app, list);
  }
  return ordered;
}

export function relativeTime(iso: string | number, now: number = Date.now()): string {
  // The controller sends updated_at as epoch seconds (float); older shapes
  // use ISO strings. Normalize both to ms before diffing.
  const t = typeof iso === 'number' ? (iso < 1e12 ? iso * 1000 : iso) : Date.parse(iso);
  if (Number.isNaN(t)) return String(iso);
  const diffMs = now - t;
  if (diffMs < 0) return 'just now';
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function newSessionId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `sess-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e6)}`;
  }
}

export function Sidebar({
  activeSessionId,
  onNewChat,
  onResume,
}: {
  activeSessionId: string | null;
  onNewChat: () => void;
  onResume: (sessionId: string, messages: ChatMessage[], opened: OpenedFile | null) => void;
}) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [resuming, setResuming] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setConversations(await fetchConversations());
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not load conversations');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleResume(conv: ConversationSummary) {
    setResuming(conv.id);
    setError(null);
    try {
      const history = await loadHistory(conv.id);
      const messages = historyToMessages(history);
      let opened: OpenedFile | null = null;
      const docId = conv.doc_ids[0];
      if (docId) {
        try {
          opened = await fetchOpenedFile(docId, conv.id);
        } catch {
          logger.warn('sidebar.rebind-failed', { doc_id: docId });
        }
      }
      onResume(conv.id, messages, opened);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not resume conversation');
    } finally {
      setResuming(null);
    }
  }

  async function handleDelete(id: string) {
    setError(null);
    try {
      await deleteConversation(id);
      setConversations((cs) => cs.filter((c) => c.id !== id));
      setConfirmDelete(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    }
  }

  const groups = groupConversations(conversations);

  return (
    <nav className="sidebar" aria-label="Conversations" data-testid="sidebar">
      <button type="button" className="plaza-button-primary" onClick={onNewChat}>
        New chat
      </button>
      {loading && <p className="muted tiny">Loading conversations…</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!loading &&
        [...groups.entries()].map(([label, items]) => (
          <section key={label} aria-label={`${label} conversations`}>
            <h3 className="muted tiny" data-testid={`group-${label}`}>
              {label} ({items.length})
            </h3>
            <ul>
              {items.map((c) => (
                <li key={c.id} data-testid="conversation-item">
                  <button
                    type="button"
                    aria-current={activeSessionId === c.id ? 'true' : undefined}
                    disabled={resuming === c.id}
                    onClick={() => void handleResume(c)}
                    title={c.title}
                  >
                    <strong>{c.title}</strong>{' '}
                    <span className="muted tiny">
                      {relativeTime(c.updated_at)} · {c.message_count} msgs
                    </span>{' '}
                    {c.doc_ids.length > 0 && <span className="muted tiny" title="Has attached file">📎</span>}
                  </button>{' '}
                  {confirmDelete === c.id ? (
                    <span>
                      <button type="button" onClick={() => void handleDelete(c.id)} aria-label={`Confirm delete ${c.title}`}>
                        Confirm
                      </button>{' '}
                      <button type="button" onClick={() => setConfirmDelete(null)}>
                        Keep
                      </button>
                    </span>
                  ) : (
                    <button type="button" onClick={() => setConfirmDelete(c.id)} aria-label={`Delete ${c.title}`}>
                      🗑
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      {!loading && conversations.length === 0 && !error && (
        <p className="muted tiny">No conversations yet.</p>
      )}
    </nav>
  );
}
