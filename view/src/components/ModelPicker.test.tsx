/**
 * Model picker modal tests: small button shows the current pick, opens a
 * search modal, filters the list, picks via mouse, and degrades to mock
 * brain without a profile.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { CrafterChat } from './CrafterChat';
import { ModelPicker } from './ModelPicker';

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

function stubModels(ids: string[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ models: ids.map((id) => ({ id })), cached: false }) }),
  );
}

describe('ModelPicker modal', () => {
  it('button shows current pick + count, opens modal with search and options', async () => {
    const user = userEvent.setup();
    render(<ModelPicker models={['m-a', 'm-b']} selected={null} disabled={false} loading={false} noProfile={false} />);
    expect(screen.getByTestId('model-picker-button')).toHaveTextContent(/profile default/);
    expect(screen.getByTestId('model-count')).toHaveTextContent('2');
    await user.click(screen.getByTestId('model-picker-button'));
    expect(screen.getByTestId('model-picker-modal')).toBeInTheDocument();
    expect(screen.getByLabelText('Search models')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'm-a' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'profile default' })).toBeInTheDocument();
  });

  it('filters the list as you type and shows an empty state', async () => {
    const user = userEvent.setup();
    render(<ModelPicker models={['alpha-one', 'beta-two']} selected={null} disabled={false} loading={false} noProfile={false} />);
    await user.click(screen.getByTestId('model-picker-button'));
    await user.type(screen.getByLabelText('Search models'), 'beta');
    expect(screen.getByRole('option', { name: 'beta-two' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'alpha-one' })).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText('Search models'));
    await user.type(screen.getByLabelText('Search models'), 'zzz-nope');
    expect(screen.getByTestId('model-empty')).toBeInTheDocument();
  });

  it('picks a model and notifies the parent, closes the modal', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ModelPicker models={['m-a']} selected={null} disabled={false} loading={false} noProfile={false} onChange={onChange} />,
    );
    await user.click(screen.getByTestId('model-picker-button'));
    await user.click(screen.getByRole('option', { name: 'm-a' }));
    expect(onChange).toHaveBeenCalledWith('m-a');
    expect(screen.queryByTestId('model-picker-modal')).not.toBeInTheDocument();
  });

  it('shows mock brain and stays disabled without a profile', () => {
    render(<ModelPicker models={[]} selected={null} disabled noProfile loading={false} />);
    expect(screen.getByTestId('model-picker-button')).toBeDisabled();
    expect(screen.getByTestId('model-current')).toHaveTextContent('mock brain');
  });
});

describe('composer model picker (wired)', () => {
  it('chat renders the picker button fed from the profile-models endpoint', async () => {
    stubModels(['m-a', 'm-b']);
    render(<CrafterChat {...BASE} />);
    await waitFor(() => expect(screen.getByTestId('model-count')).toHaveTextContent('2'));
  });

  it('shows the selected model in the button + status line', async () => {
    stubModels(['m-a']);
    render(<CrafterChat {...BASE} selectedModel="m-a" profileLabel="Local" />);
    await waitFor(() => expect(screen.getByTestId('model-current')).toHaveTextContent('m-a'));
    expect(document.body.textContent).toContain('m-a · Local');
  });

  it('falls back to mock brain when no profile is active', () => {
    render(<CrafterChat {...BASE} profileId={null} />);
    expect(screen.getByTestId('model-picker-button')).toBeDisabled();
    expect(screen.getByTestId('model-current')).toHaveTextContent('mock brain');
  });

  it('displays the answering model from response.started', () => {
    render(<CrafterChat {...BASE} answeringModel="m-started" />);
    expect(screen.getByTestId('answering-model')).toHaveTextContent('answering with m-started');
  });
});
