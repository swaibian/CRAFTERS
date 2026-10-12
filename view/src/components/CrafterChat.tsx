/**
 * CrafterChat (TC-A-01 thread + TC-B-01 streaming/pictures).
 *
 * Why (stories #1–#3): the center thread — user/assistant/reasoning/toolcall
 * blocks, composer with text + picture attach, working pill while streaming,
 * Enter-to-send / Esc-to-cancel, reduced-motion-aware auto-scroll.
 */

import { useEffect, useRef, useState } from 'react';
import { downloadResultUrl, fetchProfileModels } from '../lib/api';
import { nextId, type ChatMessage } from '../lib/chat';
import { resizeImage } from '../lib/image';
import { logger } from '../lib/logger';
import { Markdown } from './Markdown';
import { ToolcallBlockView } from './ToolcallView';

export function CrafterChat({
  messages,
  streaming,
  streamError,
  chatEnabled,
  sessionId,
  docId,
  profileId,
  profileLabel,
  teamId,
  answeringModel,
  selectedModel,
  onModelChange,
  verifyAvailable,
  onSend,
  onCancel,
  onVerifyCommand,
}: {
  messages: ChatMessage[];
  streaming: boolean;
  streamError: string | null;
  chatEnabled: boolean;
  sessionId: string | null;
  docId: string | null;
  profileId: string | null;
  /** Human-readable profile label for the status line (falls back to id). */
  profileLabel?: string | null;
  teamId: string | null;
  /** Answering model from the latest response.started (thread header). */
  answeringModel?: string | null;
  /** Currently selected model override (composer select). */
  selectedModel?: string | null;
  onModelChange?: (model: string | null) => void;
  verifyAvailable: Record<string, boolean>;
  onSend: (text: string, imageDataUrl?: string) => void;
  onCancel: () => void;
  onVerifyCommand: (command: string) => void;
}) {
  const [draft, setDraft] = useState('');
  const [attached, setAttached] = useState<string | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const reducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;

  // Model options follow the active profile; no profile → "mock brain" state.
  useEffect(() => {
    if (!profileId) {
      setModels([]);
      return;
    }
    let cancelled = false;
    setModelsLoading(true);
    fetchProfileModels(profileId)
      .then((data) => {
        if (!cancelled) setModels(data.models.map((m) => m.id));
      })
      .catch(() => {
        if (!cancelled) setModels([]);
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [profileId]);

  useEffect(() => {
    const el = threadRef.current;
    if (!el) return;
    if (typeof el.scrollTo === 'function') {
      el.scrollTo({ top: el.scrollHeight, behavior: reducedMotion ? 'auto' : 'smooth' });
    } else {
      el.scrollTop = el.scrollHeight; // jsdom / older engines without scrollTo
    }
  }, [messages, reducedMotion]);

  async function handleAttach(file: File) {
    setAttachError(null);
    try {
      const dataUrl = await resizeImage(file, 1024);
      setAttached(dataUrl);
      logger.info('chat.image.attached', { resized: true });
    } catch (err) {
      setAttachError(err instanceof Error ? err.message : 'Could not attach image');
    }
  }

  function send() {
    const text = draft.trim();
    if ((!text && !attached) || streaming || !chatEnabled) return;
    onSend(text, attached ?? undefined);
    setDraft('');
    setAttached(null);
  }

  return (
    <section className="chat" aria-label="Chat thread">
      {answeringModel && (
        <p className="muted tiny" data-testid="answering-model">
          answering with {answeringModel}
        </p>
      )}
      <div className="thread" ref={threadRef} role="log" aria-live="polite" aria-label="Messages">
        {messages.length === 0 && (
          <p className="muted">
            {chatEnabled
              ? 'Ask about the opened file — e.g. “resize to 800px”.'
              : 'Pick an app and drop a file to enable chat.'}
          </p>
        )}
        {messages.map((m) => (
          <article key={m.id} className={`msg ${m.role}`} data-testid={`msg-${m.role}`}>
            {m.role === 'assistant' && (
              <img
                src="/assets/swaibian_avatar_black.svg"
                alt=""
                aria-hidden="true"
                className="msg-avatar"
              />
            )}            {m.role === 'user' ? (
              <>
                {m.text && <p>{m.text}</p>}
                {m.imageUrl && <img src={m.imageUrl} alt={m.imageAlt ?? 'Attached image'} className="chat-img" />}
              </>
            ) : (
              <>
                {(m.blocks ?? []).map((b) => {
                  if (b.kind === 'text') return <Markdown key={b.id} text={b.text} />;
                  if (b.kind === 'reasoning')
                    return (
                      <details key={b.id} className="reasoning">
                        <summary>reasoning</summary>
                        <Markdown text={b.text} />
                      </details>
                    );
                  return (
                    <ToolcallBlockView
                      key={b.id}
                      block={b}
                      sessionId={sessionId}
                      docId={docId}
                      verifyAvailable={verifyAvailable}
                      onVerifyCommand={onVerifyCommand}
                    />
                  );
                })}
                {m.text && <Markdown text={m.text} />}
                {m.pending && (
                  <span className="working-pill" role="status">
                    working…
                  </span>
                )}
                {m.error && (
                  <p className="error" role="alert">
                    {m.error}
                  </p>
                )}
              </>
            )}
          </article>
        ))}
        {streamError && !streaming && (
          <p className="error" role="alert">
            {streamError}
          </p>
        )}
      </div>

      {docId && (
        <p className="muted">
          <a href={downloadResultUrl(docId, sessionId ?? undefined)} download>
            Download result
          </a>
        </p>
      )}

      <div className="composer">
        <label className="muted tiny">
          Model
          <select
            aria-label="Chat model"
            value={selectedModel ?? ''}
            disabled={!profileId || modelsLoading || models.length === 0}
            onChange={(e) => onModelChange?.(e.target.value || null)}
            title={!profileId ? 'mock brain — pick a profile in Settings' : undefined}
          >
            <option value="">{!profileId ? 'mock brain' : modelsLoading ? 'loading…' : 'profile default'}</option>
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        {attached && (
          <div className="attach-preview">
            <img src={attached} alt="Image staged to send" />
            <button type="button" aria-label="Remove attached image" onClick={() => setAttached(null)}>
              ✕
            </button>
          </div>
        )}
        <textarea
          aria-label="Chat message"
          placeholder={chatEnabled ? 'Message the agent…' : 'Open a file to start chatting'}
          value={draft}
          disabled={!chatEnabled}
          rows={2}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            } else if (e.key === 'Escape' && streaming) {
              e.preventDefault();
              onCancel();
            }
          }}
        />
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          hidden
          aria-label="Attach a picture"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleAttach(f);
            e.target.value = '';
          }}
        />
        <button type="button" disabled={!chatEnabled} title="Attach a picture" onClick={() => fileRef.current?.click()}>
          📎
        </button>
        {streaming ? (
          <button type="button" onClick={onCancel} aria-label="Cancel streaming">
            Stop
          </button>
        ) : (
          <button
            type="button"
            className="plaza-button-primary"
            onClick={send}
            disabled={!chatEnabled || (!draft.trim() && !attached)}
            aria-label="Send message"
          >
            Send
          </button>
        )}
      </div>
      {attachError && (
        <p className="error" role="alert">
          {attachError}
        </p>
      )}
      <p className="muted tiny">
        session: {sessionId ?? '—'} · {selectedModel ?? 'profile default'} · {profileLabel ?? profileId ?? 'default'} · team: {teamId ?? '—'}
      </p>
    </section>
  );
}

export function useChatMessages() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const appendMessage = (m: ChatMessage) => setMessages((prev) => [...prev, m]);
  const patchMessage = (id: string, patch: (m: ChatMessage) => ChatMessage) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? patch(m) : m)));
  const pushNotice = (text: string) =>
    appendMessage({ id: nextId('sys'), role: 'assistant', text });
  return { messages, setMessages, appendMessage, patchMessage, pushNotice };
}
