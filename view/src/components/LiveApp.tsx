/**
 * LiveApp: use a document open in a running Craft desktop app as the chat object.
 *
 * Why (live chat objects): the desktop app is started with `--control` and
 * the controller snapshots its window into the session on attach — the
 * returned OpenedFile binds chat exactly like an upload (same doc_id flow,
 * thumbnail, download, verify). When the app is down the exact start
 * command is shown so the user can launch it and hit Refresh.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  ApiError,
  attachLiveDoc,
  fetchLiveDocuments,
  fetchLiveStatus,
  launchLiveApp,
  type LiveAppStatus,
  type LiveDocument,
  type OpenedFile,
} from '../lib/api';
import { logger } from '../lib/logger';

function docLabel(doc: LiveDocument): string {
  const dims = doc.width != null && doc.height != null ? ` · ${doc.width}×${doc.height}` : '';
  const dirty = doc.dirty ? ' · ●unsaved' : '';
  const active = doc.active ? ' · active' : '';
  return `${doc.name}${dims}${dirty}${active}`;
}

export function LiveApp({
  sessionId,
  onOpened,
}: {
  /** Active chat session; sent as session_id on attach. */
  sessionId?: string;
  onOpened: (f: OpenedFile) => void;
}) {
  const [status, setStatus] = useState<LiveAppStatus[] | null>(null);
  const [docs, setDocs] = useState<Record<string, LiveDocument[]>>({});
  const [busyApp, setBusyApp] = useState<string | null>(null);
  const [attaching, setAttaching] = useState<string | null>(null);
  const [launching, setLaunching] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      setStatus(await fetchLiveStatus());
    } catch (err) {
      setStatus(null);
      setError(
        err instanceof ApiError && err.unreachable
          ? 'Controller unreachable — live apps need the controller (:8790).'
          : `Could not reach live apps: ${err instanceof Error ? err.message : 'unknown error'}`,
      );
      logger.warn('live.status.failed', {});
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function launch(app: string) {
    setLaunching(app);
    setError(null);
    try {
      await launchLiveApp(app);
      logger.info('live.launched', { app });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not launch ${app}`);
      logger.warn('live.launch.failed', { app });
    } finally {
      setLaunching(null);
    }
  }

  async function showDocuments(app: string) {
    setBusyApp(app);
    setError(null);
    try {
      const { documents } = await fetchLiveDocuments(app);
      setDocs((prev) => ({ ...prev, [app]: documents }));
      if (documents.length === 0) setError(`${app} has no open documents.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not list ${app} documents`);
      logger.warn('live.documents.failed', { app });
    } finally {
      setBusyApp(null);
    }
  }

  async function useAsChatObject(app: string, doc: LiveDocument) {
    setAttaching(`${app}:${doc.index}`);
    setError(null);
    try {
      const opened = await attachLiveDoc(app, doc.index, sessionId);
      onOpened(opened);
      logger.info('live.attached', { app });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not attach the live document');
      logger.warn('live.attach.failed', { app });
    } finally {
      setAttaching(null);
    }
  }

  return (
    <div className="liveapp" aria-label="Live desktop apps">
      <button type="button" onClick={() => void refresh()} aria-label="Refresh live app status">
        Refresh
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {status === null && !error && <p className="muted tiny">Checking live apps…</p>}
      {status !== null && status.length === 0 && <p className="muted tiny">No live apps configured.</p>}
      {(status ?? []).map((entry) => {
        const appDocs = docs[entry.app] ?? null;
        return (
          <div key={entry.app} className="liveapp-row" data-testid={`liveapp-${entry.app}`}>
            <span
              className={entry.running ? 'app-dot' : 'app-dot'}
              aria-hidden="true"
              data-ready={entry.running}
            />
            <strong>{entry.app}</strong>
            <span className="muted tiny">{entry.running ? 'running' : 'down'}</span>
            {entry.running ? (
              <button
                type="button"
                disabled={busyApp === entry.app}
                onClick={() => void showDocuments(entry.app)}
                aria-label={`List open documents in ${entry.app}`}
              >
                {busyApp === entry.app ? 'Listing…' : appDocs ? 'Reload' : 'Show open documents'}
              </button>
            ) : entry.launchable ? (
              <>
                <button
                  type="button"
                  className="plaza-button-primary"
                  disabled={launching === entry.app}
                  onClick={() => void launch(entry.app)}
                  aria-label={`Launch ${entry.app}`}
                >
                  {launching === entry.app ? 'Launching…' : 'Launch'}
                </button>{' '}
                {entry.hint && (
                  <p className="muted tiny liveapp-hint">
                    Manual start: <code>{entry.hint}</code>
                  </p>
                )}
              </>
            ) : (
              entry.hint && (
                <p className="muted tiny liveapp-hint">
                  Start it with <code>{entry.hint}</code> then hit Refresh.
                </p>
              )
            )}
            {appDocs && (
              <ul className="liveapp-docs">
                {appDocs.map((doc) => {
                  const key = `${entry.app}:${doc.index}`;
                  return (
                    <li key={key}>
                      <span title={docLabel(doc)}>{docLabel(doc)}</span>{' '}
                      <button
                        type="button"
                        disabled={attaching === key}
                        onClick={() => void useAsChatObject(entry.app, doc)}
                        aria-label={`Use ${doc.name} as chat object`}
                      >
                        {attaching === key ? 'Attaching…' : 'Use as chat object'}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
