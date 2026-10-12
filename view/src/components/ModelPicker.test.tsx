/**
 * Model picker tests: composer select renders options from the mocked
 * profile-models endpoint, selection is reflected in the UI, the fallback
 * (mock brain / profile default) shows when fetch fails, and the answering
 * model from response.started renders in the thread header.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { CrafterChat } from './CrafterChat';

afterEach(() => {
  vi.unstubAllGlobals();
});

const BASE = {
  messages: [],
  streaming: false,
  streamError: null,
  chatEnabled: true,
  sessionId: 's1',
  docId: 'd1',
  profileId: 'p1',
  teamId: null,
  verifyAvailable: {},
  onSend: () => {},
  onCancel: () => {},
  onVerifyCommand: () => {},
};

describe('composer model picker', () => {
  it('renders options from the mocked profile-models endpoint', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ models: [{ id: 'm-a' }, { id: 'm-b' }], cached: false }) }),
    );
    render(<CrafterChat {...BASE} />);
    await waitFor(() => expect(screen.getByRole('option', { name: 'm-a' })).toBeInTheDocument());
    expect(screen.getByRole('option', { name: 'm-b' })).toBeInTheDocument();
  });

  it('notifies the parent when the selection changes', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ models: [{ id: 'm-a' }], cached: false }) }),
    );
    const onModelChange = vi.fn();
    render(<CrafterChat {...BASE} selectedModel={null} onModelChange={onModelChange} />);
    const select = await waitFor(() => screen.getByLabelText('Chat model'));
    await user.selectOptions(select, 'm-a');
    expect(onModelChange).toHaveBeenCalledWith('m-a');
  });

  it('shows the selected model in the muted status line', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ models: [{ id: 'm-a' }], cached: false }) }),
    );
    render(<CrafterChat {...BASE} selectedModel="m-a" profileLabel="Local" />);
    await waitFor(() => expect(screen.getByLabelText('Chat model')).toBeInTheDocument());
    expect(document.body.textContent).toContain('m-a · Local');
  });

  it('falls back to mock brain when no profile is active', () => {
    render(<CrafterChat {...BASE} profileId={null} />);
    const select = screen.getByLabelText('Chat model');
    expect(select).toBeDisabled();
    expect(screen.getByRole('option', { name: 'mock brain' })).toBeInTheDocument();
  });

  it('falls back to profile default when the models fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('down')));
    render(<CrafterChat {...BASE} />);
    await waitFor(() => expect(screen.getByLabelText('Chat model')).toBeDisabled());
    expect(screen.getByRole('option', { name: 'profile default' })).toBeInTheDocument();
  });

  it('displays the answering model from response.started', () => {
    render(<CrafterChat {...BASE} answeringModel="m-started" />);
    expect(screen.getByTestId('answering-model')).toHaveTextContent('answering with m-started');
  });
});
