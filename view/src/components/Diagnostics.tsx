/**
 * Diagnostics page (#/diagnostics).
 *
 * Why: four service status cards (Gateway/Controller/Scaico/LiteLLM) with
 * ok/down/unconfigured + latency + detail + last-checked, a Refresh button,
 * a recent-events table, a Scaico "Test saved key" button (empty input tests
 * the stored server-side key), and the view log viewer (ring buffer in
 * lib/logger.ts) with level filter + Clear. Keys never render — only
 * ok/latency/error strings.
 */

import { useCallback, useEffect, useState } from 'react';
import { fetchDiagnostics, testScaicoKey, type DiagnosticsData } from '../lib/api';
import { clearViewLogs, getViewLogs, type ViewLogRecord } from '../lib/logger';

const CARDS = [
  { key: 'gateway', title: 'Gateway · ArtCraft-apps connector' },
  { key: 'controller', title: 'Controller' },
  { key: 'scaico', title: 'Scaico API' },
  { key: 'litellm', title: 'LiteLLM endpoint' },
] as const;

type CardKey = (typeof CARDS)[number]['key'];

function cardStatus(check: { ok: boolean; configured?: boolean } | undefined): string {
  if (!check) return 'down';
  if (check.configured === false) return 'unconfigured';
  return check.ok ? 'ok' : 'down';
}

const LEVELS = ['all', 'debug', 'info', 'warn', 'error'] as const;

export function Diagnostics() {
  const [data, setData] = useState<DiagnosticsData | null>(null);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scaicoResult, setScaicoResult] = useState<string | null>(null);
  const [scaicoTesting, setScaicoTesting] = useState(false);
  const [levelFilter, setLevelFilter] = useState<(typeof LEVELS)[number]>('all');
  const [logs, setLogs] = useState<ViewLogRecord[]>(() => getViewLogs());

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await fetchDiagnostics();
      setData(d);
      setCheckedAt(new Date().toISOString());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Diagnostics fetch failed');
    } finally {
      setLoading(false);
      setLogs(getViewLogs());
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleScaicoTest() {
    setScaicoTesting(true);
    setScaicoResult(null);
    try {
      const res = await testScaicoKey();
      setScaicoResult(
        res.ok ? `Saved key ok${res.latency_ms != null ? ` (${res.latency_ms} ms)` : ''}.` : `Saved key failed: ${res.error ?? 'unknown error'}`,
      );
    } catch (err) {
      setScaicoResult(err instanceof Error ? err.message : 'Scaico test failed');
    } finally {
      setScaicoTesting(false);
      setLogs(getViewLogs());
    }
  }

  const visibleLogs = levelFilter === 'all' ? logs : logs.filter((l) => l.level === levelFilter);

  return (
    <div className="settings" data-testid="diagnostics-view">
      <h2>Diagnostics</h2>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="row">
        <button type="button" onClick={() => void refresh()} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
        {checkedAt && <span className="muted tiny">last checked: {checkedAt}</span>}
      </div>

      <section aria-label="Service status">
        <h3>Status</h3>
        <ul className="profile-list">
          {CARDS.map((card) => {
            const check = data?.checks[card.key as CardKey];
            const status = cardStatus(check);
            return (
              <li key={card.key} data-testid={`diag-card-${card.key}`}>
                <strong>{card.title}</strong>{' '}
                <span className={status === 'ok' ? 'ok' : status === 'unconfigured' ? 'muted' : 'error'}>
                  {status}
                </span>
                {check?.latency_ms != null && <span className="muted"> · {check.latency_ms} ms</span>}
                {check?.detail && <span className="muted"> · {check.detail}</span>}
                {card.key === 'scaico' && (
                  <button type="button" onClick={() => void handleScaicoTest()} disabled={scaicoTesting}>
                    {scaicoTesting ? 'Testing…' : 'Test saved key'}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
        {scaicoResult && (
          <p className="muted" role="status">
            {scaicoResult}
          </p>
        )}
      </section>

      <section aria-label="Recent events">
        <h3>Recent events</h3>
        {!data || data.recent.length === 0 ? (
          <p className="muted">No recent events.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Service</th>
                <th>OK</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {data.recent.map((e, i) => (
                <tr key={`${e.at}-${e.service}-${i}`}>
                  <td>{e.at}</td>
                  <td>{e.service}</td>
                  <td>{e.ok ? 'yes' : 'no'}</td>
                  <td>{e.detail ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-label="View logs">
        <h3>View logs</h3>
        <div className="row">
          <label className="muted tiny">
            Level
            <select aria-label="Log level filter" value={levelFilter} onChange={(e) => setLevelFilter(e.target.value as typeof levelFilter)}>
              {LEVELS.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => {
              clearViewLogs();
              setLogs(getViewLogs());
            }}
          >
            Clear
          </button>
        </div>
        {visibleLogs.length === 0 ? (
          <p className="muted">No log records.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Level</th>
                <th>Event</th>
                <th>Fields</th>
              </tr>
            </thead>
            <tbody>
              {visibleLogs.map((l, i) => (
                <tr key={`${l.at}-${l.event}-${i}`}>
                  <td>{l.at}</td>
                  <td>{l.level}</td>
                  <td>{l.event}</td>
                  <td>{JSON.stringify(l.fields)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
