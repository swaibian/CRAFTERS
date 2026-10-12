/**
 * Dropzone (TC-A-01): drag/drop + file input → POST /api/files/open.
 *
 * Why (story #1): dropping a real file opens it in the selected app and binds
 * the chat to doc_id+session_id. Requires an armed app; unreachable controller
 * surfaces an inline error, never a crash.
 */

import { useEffect, useRef, useState } from 'react';
import { ApiError, openFile, thumbnailUrl, type OpenedFile } from '../lib/api';
import { logger } from '../lib/logger';

function inspectSummary(inspect: Record<string, unknown>): string {
  const keys = Object.keys(inspect);
  if (keys.length === 0) return 'No inspect metadata';
  const parts: string[] = [];
  for (const k of ['pages', 'width', 'height', 'mode', 'format', 'rows', 'cols', 'sheets']) {
    if (inspect[k] !== undefined) parts.push(`${k}: ${String(inspect[k])}`);
  }
  for (const k of keys) {
    if (parts.length >= 4) break;
    if (!parts.some((p) => p.startsWith(k))) parts.push(`${k}: ${String(inspect[k])}`);
  }
  return parts.join(' · ');
}

export function Dropzone({
  app,
  opened,
  sessionId,
  onOpened,
}: {
  app: string | null;
  opened: OpenedFile | null;
  /** Active chat session; sent as the session_id form field on open. */
  sessionId?: string;
  onOpened: (f: OpenedFile) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewLarge, setPreviewLarge] = useState(false);
  const [previewHidden, setPreviewHidden] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const previewSrc = opened ? opened.thumbnail_url ?? thumbnailUrl(opened.doc_id, sessionId) : null;

  // Reset preview state whenever a different file is opened.
  useEffect(() => {
    setPreviewLarge(false);
    setPreviewHidden(false);
  }, [opened?.doc_id]);

  // Esc closes the enlarged preview.
  useEffect(() => {
    if (!previewLarge) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPreviewLarge(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [previewLarge]);

  async function handleFile(file: File) {
    if (!app) {
      setError('Pick an app first, then drop a file.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const openedFile = await openFile(file, app, sessionId);
      onOpened(openedFile);
    } catch (err) {
      const msg =
        err instanceof ApiError && err.unreachable
          ? 'Controller unreachable — file open needs the controller (:8790). Retry when it is up.'
          : `Could not open file: ${err instanceof Error ? err.message : 'unknown error'}`;
      setError(msg);
      logger.warn('file.open.failed', { app });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dropzone-wrap">
      <div
        className={dragOver ? 'dropzone over' : 'dropzone'}
        role="button"
        tabIndex={0}
        aria-label={app ? `Drop a file to open in ${app}` : 'Pick an app before dropping a file'}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void handleFile(file);
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click();
        }}
      >
        {busy ? 'Opening…' : app ? `Drop file here or click to browse (→ ${app})` : 'Select an app above first'}
        <input
          ref={inputRef}
          type="file"
          hidden
          aria-label="Choose a file to open"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
            e.target.value = '';
          }}
        />
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {opened && (
        <div className="opened-file" data-testid="opened-file-header">
          <div>
            <strong>{opened.name}</strong>
            <div className="muted">
              {opened.app} · {inspectSummary(opened.inspect)}
            </div>
          </div>
          {previewSrc && !previewHidden && (
            <button
              type="button"
              className="preview-card"
              onClick={() => setPreviewLarge(true)}
              aria-label={`Enlarge preview of ${opened.name}`}
              title="Click to enlarge"
            >
              <img
                src={previewSrc}
                alt={`Preview of ${opened.name}`}
                className="preview-img"
                loading="lazy"
                onError={() => setPreviewHidden(true)}
              />
              <span className="preview-zoom" aria-hidden="true">⤢</span>
            </button>
          )}
          {previewLarge && previewSrc && !previewHidden && (
            <div
              className="preview-lightbox"
              role="dialog"
              aria-modal="true"
              aria-label={`Preview of ${opened.name}`}
              onClick={() => setPreviewLarge(false)}
            >
              <img
                src={previewSrc}
                alt={`Large preview of ${opened.name}`}
                className="preview-lightbox-img"
                onError={() => {
                  setPreviewHidden(true);
                  setPreviewLarge(false);
                }}
              />
              <span className="muted tiny">Click anywhere or press Esc to close</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
