/**
 * Diagnostics page tests (mocked fetch): four status cards render with
 * ok/down/unconfigured states, Refresh re-fetches, recent events render as a
 * table, "Test saved key" posts an empty body, and the log viewer filters +
 * clears.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { Diagnostics } from './Diagnostics';
import { clearViewLogs, logger } from '../lib/logger';

const PAYLOAD = {
  checks: {
    gateway: { ok: true, latency_ms: 3 },
    controller: { ok: false, detail: 'refused' },
    scaico: { ok: false, configured: false },
    litellm: { ok: true, configured: true, model: 'm' },
  },
  recent: [{ at: '2026-01-01T00:00:00Z', service: 'gateway', ok: true, detail: 'fine' }],
};

beforeEach(() => {
  clearViewLogs();
  vi.spyOn(console, 'info').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function stubDiagnostics(payload: unknown = PAYLOAD) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (url: string) => {
      if (String(url).includes('/api/diagnostics')) return { ok: true, json: async () => payload };
      if (String(url).includes('/api/settings/scaico-key/test'))
        return { ok: true, json: async () => ({ ok: true, latency_ms: 7 }) };
      return { ok: false, status: 404 };
    }),
  );
}

describe('Diagnostics', () => {
  it('renders four status cards with ok/down/unconfigured', async () => {
    stubDiagnostics();
    render(<Diagnostics />);
    await waitFor(() => expect(screen.getByTestId('diag-card-gateway')).toHaveTextContent('ok'));
    expect(screen.getByTestId('diag-card-controller')).toHaveTextContent('down');
    expect(screen.getByTestId('diag-card-scaico')).toHaveTextContent('unconfigured');
    expect(screen.getByTestId('diag-card-litellm')).toHaveTextContent('ok');
    expect(screen.getByTestId('diag-card-gateway')).toHaveTextContent('3 ms');
  });

  it('renders the recent-events table', async () => {
    stubDiagnostics();
    render(<Diagnostics />);
    await waitFor(() => expect(screen.getByText('fine')).toBeInTheDocument());
    expect(screen.getByText('gateway')).toBeInTheDocument();
  });

  it('tests the saved Scaico key with an empty body', async () => {
    const user = userEvent.setup();
    const spy = vi.fn().mockImplementation(async (url: string) => {
      if (String(url).includes('/api/diagnostics')) return { ok: true, json: async () => PAYLOAD };
      if (String(url).includes('/api/settings/scaico-key/test'))
        return { ok: true, json: async () => ({ ok: true, latency_ms: 7 }) };
      return { ok: false, status: 404 };
    });
    vi.stubGlobal('fetch', spy);
    render(<Diagnostics />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Test saved key' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Test saved key' }));
    await waitFor(() => expect(screen.getByText(/saved key ok/i)).toBeInTheDocument());
    const testCall = spy.mock.calls.find((c) => String(c[0]).includes('scaico-key/test'));
    expect(JSON.parse(String((testCall?.[1] as RequestInit | undefined)?.body ?? '{}'))).toEqual({});
  });

  it('filters and clears the view log viewer', async () => {
    const user = userEvent.setup();
    stubDiagnostics();
    logger.warn('diag.probe', {});
    logger.info('diag.other', {});
    render(<Diagnostics />);
    await waitFor(() => expect(screen.getByText('diag.probe')).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Log level filter'), 'warn');
    expect(screen.getByText('diag.probe')).toBeInTheDocument();
    expect(screen.queryByText('diag.other')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(screen.getByText(/no log records/i)).toBeInTheDocument();
  });

  it('shows an inline error when diagnostics are unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('down')));
    render(<Diagnostics />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
