/**
 * CrafterChat (TC-A-01 thread + TC-B-01 streaming/pictures).
 *
 * Why (stories #1–#3): the center thread — user/assistant/reasoning/toolcall
 * blocks, composer with text + picture attach, working pill while streaming,
 * Enter-to-send / Esc-to-cancel, reduced-motion-aware auto-scroll.
 */

import { useEffect, useRef, useState } from 'react';
import { downloadResultUrl, fetchProfileModels } from '../lib/api';
import { nextId, type AssistantBlock, type ChatMessage, type ReasoningBlock } from '../lib/chat';
import { resizeImage } from '../lib/image';
import { logger } from '../lib/logger';
import { Markdown } from './Markdown';
import { ModelPicker } from './ModelPicker';
import { ToolcallBlockView } from './ToolcallView';

function stepPreview(text: string): string {
  const compact = text.replace(/\s+/g, ' ').trim();
  return compact.length > 110 ? `${compact.slice(0, 107)}…` : compact;
}

/**
 * One reasoning step. The step text must render exactly once: the compact
 * preview is the collapsed affordance, the Markdown body is the expanded
 * content — never both (an open step used to show its text twice).
 */
function ReasoningStepView({
  step,
  index,
  defaultOpen,
}: {
  step: ReasoningBlock;
  index: number;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details
      className="reasoning-step"
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      data-testid="reasoning-step"
    >
      <summary>
        <span className="step-index">Step {index + 1}</span>
        {!open && <span className="step-preview">{stepPreview(step.text)}</span>}
      </summary>
      {open && <Markdown text={step.text} />}
    </details>
  );
}

function AssistantBlocks({
  blocks,
  sessionId,
  docId,
  verifyAvailable,
  onVerifyCommand,
}: {
  blocks: AssistantBlock[];
  sessionId: string | null;
  docId: string | null;
  verifyAvailable: Record<string, boolean>;
  onVerifyCommand: (command: string) => void;
}) {
  const reasoning = blocks.filter((block) => block.kind === 'reasoning');
  const toolcalls = blocks.filter((block) => block.kind === 'toolcall');
  let reasoningRendered = false;
  let toolcallsRendered = false;

  return (
    <>
      {blocks.map((block) => {
        if (block.kind === 'text') return <Markdown key={block.id} text={block.text} />;
        if (block.kind === 'final') {
          return (
            <div key={block.id} className="final-response" data-testid="final-response">
              <span className="final-response-label">Final response</span>
              <Markdown text={block.text} />
            </div>
          );
        }

        if (block.kind === 'reasoning') {
          if (reasoningRendered) return null;
          reasoningRendered = true;
          return (
            <details key="reasoning-group" className="activity-group reasoning-group" open>
              <summary>
                <span>Reasoning</span>
                <span className="activity-count">{reasoning.length}</span>
              </summary>
              <div className="activity-list">
                {reasoning.map((step, index) => {
                  const recent = index >= reasoning.length - 2;
                  return (
                    <ReasoningStepView
                      key={`${step.id}-${recent ? 'recent' : 'older'}`}
                      step={step}
                      index={index}
                      defaultOpen={recent}
                    />
                  );
                })}
              </div>
            </details>
          );
        }

        if (toolcallsRendered) return null;
        toolcallsRendered = true;
        return (
          <details key="toolcall-group" className="activity-group toolcall-group">
            <summary>
              <span>Tool calls</span>
              <span className="activity-count">{toolcalls.length}</span>
            </summary>
            <div className="activity-list">
              {toolcalls.map((tool) => (
                <ToolcallBlockView
                  key={tool.id}
                  block={tool}
                  sessionId={sessionId}
                  docId={docId}
                  verifyAvailable={verifyAvailable}
                  onVerifyCommand={onVerifyCommand}
                />
              ))}
            </div>
          </details>
        );
      })}
    </>
  );
}

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
  activeProfileDefaultModel,
  liveHint,
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
  /** Profile's stored default (button shows the id, not "profile default"). */
  activeProfileDefaultModel?: string | null;
  /** "Working on app · doc N (live)" for source === "live" chat objects. */
  liveHint?: string | null;
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
      <div className="chat-toolbar">
        {answeringModel ? (
          <p className="muted tiny" data-testid="answering-model">
            answering with {answeringModel}
          </p>
        ) : (
          <span />
        )}
        <ModelPicker
          models={models}
          selected={selectedModel ?? null}
          activeProfileDefaultModel={activeProfileDefaultModel ?? null}
          disabled={!profileId || (modelsLoading && models.length === 0)}
          loading={modelsLoading}
          noProfile={!profileId}
          onChange={onModelChange}
        />
      </div>
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
            )}
            {m.role === 'user' ? (
              <>
                {m.text && <p>{m.text}</p>}
                {m.imageUrl && <img src={m.imageUrl} alt={m.imageAlt ?? 'Attached image'} className="chat-img" />}
              </>
            ) : (
              <div className="msg-body">
                <AssistantBlocks
                  blocks={m.blocks ?? []}
                  sessionId={sessionId}
                  docId={docId}
                  verifyAvailable={verifyAvailable}
                  onVerifyCommand={onVerifyCommand}
                />
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
              </div>
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
      {liveHint && (
        <p className="muted tiny" data-testid="live-hint">
          {liveHint}
        </p>
      )}
      <p className="muted tiny">
        session: {sessionId ?? '—'} · {selectedModel ?? activeProfileDefaultModel ?? 'profile default'} · {profileLabel ?? profileId ?? 'default'} · team: {teamId ?? '—'}
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
