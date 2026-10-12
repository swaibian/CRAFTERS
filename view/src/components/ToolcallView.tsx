/**
 * ToolcallView (TC-A-02): inline toolcall blocks + right collapsible detail.
 *
 * Why (story #2, #7): users must see do/see/reason steps and trust agent
 * edits. Args render compactly and redacted (secret-looking keys hidden):
 * a `command` arg shows inline after the tool name (`command_run
 * image.imageRotation.90cw`), every other arg is one `key: value` line —
 * never a raw JSON blob. Verify actions (Snapshot / Restore / Record view)
 * call POST /api/verify/* when present, else render disabled with a tooltip
 * and fall back to chat commands.
 */

import { useState } from 'react';
import { VERIFY_ACTIONS, runVerifyAction } from '../lib/api';
import { redactArgs, type ToolCallBlock } from '../lib/chat';
import { logger } from '../lib/logger';

/** One arg value as a single compact line (scalars bare, objects JSON). */
function formatArgValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value !== null && typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function ToolcallBlockView({
  block,
  sessionId,
  docId,
  verifyAvailable,
  onVerifyCommand,
}: {
  block: ToolCallBlock;
  sessionId: string | null;
  docId: string | null;
  verifyAvailable: Record<string, boolean>;
  onVerifyCommand: (command: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [verifyMsg, setVerifyMsg] = useState<string | null>(null);
  const [verifyBusy, setVerifyBusy] = useState<string | null>(null);

  async function handleVerify(actionId: string) {
    if (!sessionId) {
      setVerifyMsg('Open a file first — verify needs a session.');
      return;
    }
    if (!verifyAvailable[actionId]) {
      // Fallback: route through chat as a command (controller without /api/verify/*).
      onVerifyCommand(`/${actionId} ${docId ?? ''}`.trim());
      return;
    }
    setVerifyBusy(actionId);
    setVerifyMsg(null);
    try {
      const res = await runVerifyAction(actionId, { session_id: sessionId, doc_id: docId ?? undefined });
      setVerifyMsg(res.summary || `${actionId} ok`);
    } catch (err) {
      setVerifyMsg(`Verify failed: ${err instanceof Error ? err.message : 'unknown'}`);
      logger.warn('verify.failed', { action: actionId });
    } finally {
      setVerifyBusy(null);
    }
  }

  const statusLabel = block.status === 'running' ? 'running' : block.status === 'done' ? 'ok' : 'error';
  const redacted = redactArgs(block.args);
  const command = typeof redacted.command === 'string' ? redacted.command : null;
  const argRows = Object.entries(redacted).filter(([key]) => key !== 'command');

  return (
    <div className={`toolcall status-${block.status}`} data-testid="toolcall-block">
      <button
        type="button"
        className="toolcall-head"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="toolcall-dot" aria-hidden="true" />
        <code className="toolcall-name">{block.name}</code>
        {command && (
          <>
            {' '}
            <code className="toolcall-command">{command}</code>
          </>
        )}
        <span className="muted">· {statusLabel}</span>
        <span className="muted">{open ? '▾' : '▸'}</span>
      </button>
      {argRows.length > 0 && (
        <div className="toolcall-args" data-testid="toolcall-args">
          {argRows.map(([key, value]) => (
            <div key={key} className="toolcall-arg">
              <span className="toolcall-arg-key">{key}:</span>{' '}
              <span className="toolcall-arg-value">{formatArgValue(value)}</span>
            </div>
          ))}
        </div>
      )}
      {open && (
        <div className="toolcall-detail">
          {block.result && (
            <>
              <div className="muted">result</div>
              <p>{block.result.summary}</p>
            </>
          )}
          <div className="verify-row" role="group" aria-label="Verify actions">
            {VERIFY_ACTIONS.map((a) => {
              const available = verifyAvailable[a.id] !== false;
              return (
                <button
                  key={a.id}
                  type="button"
                  disabled={verifyBusy !== null || (!available && !sessionId)}
                  title={
                    available
                      ? `${a.label} via POST ${a.endpoint}`
                      : 'Controller has no verify endpoint — sends as chat command instead'
                  }
                  onClick={() => void handleVerify(a.id)}
                >
                  {verifyBusy === a.id ? '…' : a.label}
                </button>
              );
            })}
          </div>
          {verifyMsg && <p className="muted">{verifyMsg}</p>}
        </div>
      )}
    </div>
  );
}
