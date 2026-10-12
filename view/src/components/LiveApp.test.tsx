/**
 * LiveApp tests: status rows, down-app hint, list → attach binds chat object.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { LiveApp } from './LiveApp';

const STATUS = [
  { app: 'photocraft', running: true, mode: 'bridge', launchable: true },
  { app: 'gridcraft', running: false, mode: 'down', launchable: true, last_error: 'cannot reach', hint: 'gridcraft --control 7979' },
  { app: 'pdfcraft', running: false, mode: 'down', launchable: false, hint: 'pdfcraft --control ~/.pdfcraft-control.json' },
];

const DOCS = {
  app: 'photocraft',
  running: true,
  active: 1,
  documents: [{ index: 1, name: 'second.psd', width: 48, height: 32, dirty: true, active: true }],
};

const ATTACHED = {
  doc_id: 'd9',
  app: 'photo',
  name: 'second.psd (live photocraft)',
  session_id: 's1',
  source: 'live',
  live_app: 'photocraft',
  inspect: { width: 48, height: 32, mode: 'RGB' },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(handler: (url: string, init?: RequestInit) => unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (url: string, init?: RequestInit) => ({
      ok: true,
      json: async () => handler(String(url), init),
    })),
  );
}

describe('LiveApp', () => {
  it('shows running/down rows and the start hint for down apps', async () => {
    stubFetch((url) => {
      if (url === '/api/live/status') return { apps: STATUS };
      throw new Error(`unexpected ${url}`);
    });
    render(<LiveApp sessionId="s1" onOpened={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('liveapp-photocraft')).toBeInTheDocument());
    expect(screen.getByTestId('liveapp-photocraft')).toHaveTextContent('running');
    expect(screen.getByTestId('liveapp-gridcraft')).toHaveTextContent('down');
    expect(screen.getByTestId('liveapp-gridcraft')).toHaveTextContent('gridcraft --control 7979');
  });

  it('lists open documents and attaches one as the chat object', async () => {
    const user = userEvent.setup();
    stubFetch((url, init) => {
      if (url === '/api/live/status') return { apps: STATUS };
      if (url.startsWith('/api/live/documents')) return DOCS;
      if (url === '/api/live/attach') {
        const body = JSON.parse(String(init?.body ?? '{}'));
        expect(body).toMatchObject({ app: 'photocraft', document: 1, session_id: 's1' });
        return ATTACHED;
      }
      throw new Error(`unexpected ${url}`);
    });
    const onOpened = vi.fn();
    render(<LiveApp sessionId="s1" onOpened={onOpened} />);
    await waitFor(() => expect(screen.getByTestId('liveapp-photocraft')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /list open documents/i }));
    await waitFor(() => expect(screen.getByText(/second\.psd/)).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /use second\.psd as chat object/i }));
    await waitFor(() => expect(onOpened).toHaveBeenCalledOnce());
    expect(onOpened.mock.calls[0]?.[0]).toMatchObject({ doc_id: 'd9', source: 'live' });
  });

  it('shows an inline error when the controller is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('down')));
    render(<LiveApp sessionId="s1" onOpened={() => {}} />);
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/controller unreachable/i),
    );
  });

  it('offers Launch for down TCP apps and refreshes to running', async () => {
    const user = userEvent.setup();
    const posts: string[] = [];
    let launched = false;
    stubFetch((url, init) => {
      if (url === '/api/live/status') {
        if (launched) {
          return {
            apps: [
              { app: 'photocraft', running: true, mode: 'bridge', launchable: true },
              { app: 'gridcraft', running: true, mode: 'bridge', launchable: true },
              { app: 'pdfcraft', running: false, mode: 'down', launchable: false },
            ],
          };
        }
        return { apps: STATUS };
      }
      if (url === '/api/live/launch') {
        posts.push(String(init?.body ?? ''));
        launched = true;
        return { app: 'gridcraft', running: true, mode: 'bridge' };
      }
      throw new Error(`unexpected ${url}`);
    });
    render(<LiveApp sessionId="s1" onOpened={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('liveapp-gridcraft')).toBeInTheDocument());

    // Launch button on the down TCP app, none on file-based pdfcraft.
    await user.click(screen.getByRole('button', { name: 'Launch gridcraft' }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0] ?? '{}')).toMatchObject({ app: 'gridcraft' });
    await waitFor(() =>
      expect(screen.getByTestId('liveapp-gridcraft')).toHaveTextContent('running'),
    );
    expect(screen.getByTestId('liveapp-pdfcraft')).toHaveTextContent('down');
    expect(screen.queryByRole('button', { name: 'Launch pdfcraft' })).not.toBeInTheDocument();
  });

  it('keeps the manual hint when launch fails', async () => {
    const user = userEvent.setup();
    // HTTP-style failure: ok:false with a detail message.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (url: string) => {
        if (String(url) === '/api/live/status') return { ok: true, json: async () => ({ apps: STATUS }) };
        if (String(url) === '/api/live/launch')
          return { ok: false, status: 502, json: async () => ({ detail: 'gridcraft desktop binary not found' }) };
        throw new Error(`unexpected ${url}`);
      }),
    );
    render(<LiveApp sessionId="s1" onOpened={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('liveapp-gridcraft')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Launch gridcraft' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/binary not found/i));
    // Manual hint stays visible as the fallback.
    expect(screen.getByTestId('liveapp-gridcraft')).toHaveTextContent('gridcraft --control 7979');
  });
});
