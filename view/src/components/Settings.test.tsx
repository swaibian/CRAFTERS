/**
 * Settings tests (TC-B-02): masked-key render, mailto CTA when no teams,
 * team select population, profile add flow (mocked fetch).
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { Settings } from './Settings';

beforeEach(() => {
  sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(impl: (url: string, init?: RequestInit) => unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (url: string, init?: RequestInit) => impl(url, init)),
  );
}

describe('Settings', () => {
  it('renders masked keys only, never full keys', async () => {
    stubFetch((url) => {
      if (String(url).includes('/api/teams')) return { ok: true, json: async () => ({ teams: [] }) };
      return {
        ok: true,
        json: async () => ({
          profiles: [
            { id: 'p1', label: 'Local', api_base: 'http://x', api_key_masked: 'sk-...4f2a', default_model: 'm' },
          ],
          active_profile_id: 'p1',
        }),
      };
    });
    render(<Settings />);
    await waitFor(() => expect(screen.getByTestId('profile-row')).toBeInTheDocument());
    expect(screen.getByTestId('masked-key')).toHaveTextContent('sk-...4f2a');
    expect(document.body.textContent).not.toContain('sk-live');
  });

  it('shows the mailto CTA when no Scaico teams exist', async () => {
    stubFetch((url) => {
      if (String(url).includes('/api/teams')) return { ok: true, json: async () => ({ teams: [] }) };
      return { ok: true, json: async () => ({ profiles: [], active_profile_id: null }) };
    });
    render(<Settings />);
    await waitFor(() => expect(screen.getByText(/contact@swaibian.com/i)).toBeInTheDocument());
    expect(screen.getByRole('link', { name: /contact@swaibian.com/i })).toHaveAttribute(
      'href',
      expect.stringContaining('mailto:contact@swaibian.com'),
    );
  });

  it('populates the team select when teams exist', async () => {
    stubFetch((url) => {
      if (String(url).includes('/api/teams'))
        return {
          ok: true,
          json: async () => ({ teams: [{ id: 't1', name: 'Craft Team', agents: [{ id: 'a', name: 'A' }] }] }),
        };
      return { ok: true, json: async () => ({ profiles: [], active_profile_id: null }) };
    });
    render(<Settings />);
    await waitFor(() => expect(screen.getByLabelText('Scaico team')).toBeInTheDocument());
    expect(screen.getByRole('option', { name: /craft team/i })).toBeInTheDocument();
  });

  it('adds a profile through the form', async () => {
    const user = userEvent.setup();
    stubFetch((url, init) => {
      if (String(url).includes('/api/teams')) return { ok: true, json: async () => ({ teams: [] }) };
      if (String(url).endsWith('/api/settings/profiles') && (!init || !init.method || init.method === 'GET'))
        return { ok: true, json: async () => ({ profiles: [], active_profile_id: null }) };
      return {
        ok: true,
        json: async () => ({
          id: 'p9',
          label: 'Mine',
          api_base: 'https://llm.local',
          api_key_masked: 'sk-...9z',
          default_model: 'm',
        }),
      };
    });
    render(<Settings />);
    await waitFor(() => expect(screen.getByLabelText('Profile label')).toBeInTheDocument());
    await user.type(screen.getByLabelText('Profile label'), 'Mine');
    await user.type(screen.getByLabelText('API base URL'), 'https://llm.local');
    await user.type(screen.getByLabelText('API key'), 'sk-secret-value');
    await user.type(screen.getByLabelText('Default model'), 'm');
    await user.click(screen.getByRole('button', { name: 'Add profile' }));
    await waitFor(() => expect(screen.getByTestId('profile-row')).toHaveTextContent('Mine'));
    // Full key must not leak into the DOM or sessionStorage
    expect(document.body.textContent).not.toContain('sk-secret-value');
    expect(sessionStorage.getItem('crafter.activeProfileId') ?? '').not.toContain('sk-secret');
  });

  it('offers a model dropdown after a successful Test-connection on a saved profile', async () => {
    const user = userEvent.setup();
    stubFetch((url) => {
      if (String(url).includes('/api/teams')) return { ok: true, json: async () => ({ teams: [] }) };
      if (String(url).includes('/api/settings/profiles/models'))
        return { ok: true, json: async () => ({ models: [{ id: 'm-x' }, { id: 'm-y' }], cached: false }) };
      if (String(url).includes('/api/settings/profiles/test'))
        return { ok: true, json: async () => ({ ok: true, message: 'pong' }) };
      if (String(url).includes('/api/settings/active'))
        return {
          ok: true,
          json: async () => ({
            active_profile_id: null,
            mock: true,
            gateway_endpoint: 'http://127.0.0.1:8790',
            scaico: { has_key: false, api_key_masked: '', mailto: 'contact@swaibian.com' },
            selected_team_id: null,
          }),
        };
      return {
        ok: true,
        json: async () => ({
          profiles: [
            { id: 'p1', label: 'Local', api_base: 'http://x', api_key_masked: 'sk-...4f2a', default_model: '' },
          ],
          active_profile_id: 'p1',
        }),
      };
    });
    render(<Settings />);
    await waitFor(() => expect(screen.getByTestId('profile-row')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Edit' }));
    await user.click(screen.getByRole('button', { name: 'Test connection' }));
    await waitFor(() => expect(screen.getByRole('option', { name: 'm-x' })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Default model'), 'm-y');
    expect((screen.getByLabelText('Default model') as HTMLSelectElement).value).toBe('m-y');
    // Keys stay masked throughout.
    expect(document.body.textContent).not.toContain('sk-live');
  });

  it('keeps the free-text model input when the models fetch fails', async () => {
    const user = userEvent.setup();
    stubFetch((url) => {
      if (String(url).includes('/api/teams')) return { ok: true, json: async () => ({ teams: [] }) };
      if (String(url).includes('/api/settings/profiles/models')) return { ok: false, status: 502 };
      if (String(url).includes('/api/settings/profiles/test'))
        return { ok: true, json: async () => ({ ok: true, message: 'pong' }) };
      if (String(url).includes('/api/settings/active'))
        return {
          ok: true,
          json: async () => ({
            active_profile_id: null,
            mock: true,
            gateway_endpoint: 'http://127.0.0.1:8790',
            scaico: { has_key: false, api_key_masked: '', mailto: 'contact@swaibian.com' },
            selected_team_id: null,
          }),
        };
      return {
        ok: true,
        json: async () => ({
          profiles: [
            { id: 'p1', label: 'Local', api_base: 'http://x', api_key_masked: 'sk-...4f2a', default_model: '' },
          ],
          active_profile_id: 'p1',
        }),
      };
    });
    render(<Settings />);
    await waitFor(() => expect(screen.getByTestId('profile-row')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Edit' }));
    await user.click(screen.getByRole('button', { name: 'Test connection' }));
    await waitFor(() => expect(screen.getByText(/connection ok/i)).toBeInTheDocument());
    // Free-text input (not a select) remains.
    expect(screen.getByLabelText('Default model').tagName).toBe('INPUT');
  });

  it('degrades gracefully when the controller is down', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('down')));
    render(<Settings />);
    await waitFor(() => expect(screen.getByTestId('settings-view')).toHaveTextContent(/unreachable/i));
  });

  it('persists team select + scaico key + gateway endpoint server-side', async () => {
    const user = userEvent.setup();
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    stubFetch((url, init) => {
      calls.push({ url: String(url), init });
      if (String(url).includes('/api/teams'))
        return {
          ok: true,
          json: async () => ({ teams: [{ id: 't1', name: 'Craft Team', agents: [{ id: 'a', name: 'A' }] }] }),
        };
      if (String(url).includes('/api/settings/active'))
        return {
          ok: true,
          json: async () => ({
            active_profile_id: null,
            mock: true,
            gateway_endpoint: 'http://127.0.0.1:8790',
            scaico: { has_key: false, api_key_masked: '', mailto: 'contact@swaibian.com' },
            selected_team_id: null,
          }),
        };
      return { ok: true, json: async () => ({ profiles: [], active_profile_id: null }) };
    });
    render(<Settings />);
    const teamSelect = await waitFor(() => screen.getByRole('combobox', { name: 'Scaico team' }));
    await user.selectOptions(teamSelect, 't1');
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes('/api/settings/team') && (c.init?.body as string)?.includes('t1'))).toBe(true),
    );
    await user.type(screen.getByLabelText('Scaico API key'), 'scaico-SECRET-1');
    await user.click(screen.getByRole('button', { name: 'Save Scaico key' }));
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes('/api/settings/scaico-key'))).toBe(true),
    );
    const gateway = screen.getByRole('textbox', { name: 'Gateway endpoint' });
    await user.clear(gateway);
    await user.type(gateway, 'http://127.0.0.1:9999');
    await user.click(screen.getByRole('button', { name: 'Save endpoint' }));
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes('/api/settings/gateway'))).toBe(true),
    );
  });
});
