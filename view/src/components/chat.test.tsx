/**
 * Markdown + toolcall render tests: GFM tables/code render, toolcall blocks
 * show redacted args, verify buttons fall back gracefully.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CrafterChat } from './CrafterChat';
import { Markdown } from './Markdown';
import { ToolcallBlockView } from './ToolcallView';
import type { ChatMessage, ToolCallBlock } from '../lib/chat';

const BLOCK: ToolCallBlock = {
  kind: 'toolcall',
  id: 't1',
  name: 'craft_look',
  args: { doc_id: 'd1', api_key: 'sk-should-not-show' },
  result: { ok: true, summary: 'looked fine' },
  status: 'done',
};

describe('Markdown', () => {
  it('renders GFM tables and code blocks', () => {
    render(<Markdown text={'| a | b |\n|---|---|\n| 1 | 2 |\n\n```js\nconst x = 1;\n```'} />);
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(document.querySelector('code')).toHaveTextContent('const x = 1;');
  });

  it('renders headings', () => {
    render(<Markdown text={'# Title\n\n## Section'} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Title' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Section' })).toBeInTheDocument();
  });

  it('renders bullet and numbered lists', () => {
    render(<Markdown text={'- one\n- two\n\n1. first\n2. second'} />);
    const lists = screen.getAllByRole('list');
    expect(lists).toHaveLength(2);
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['one', 'two', 'first', 'second']);
  });

  it('renders links and inline code', () => {
    render(<Markdown text={'See [docs](https://example.com) and run `craft_look`.'} />);
    const link = screen.getByRole('link', { name: 'docs' });
    expect(link).toHaveAttribute('href', 'https://example.com');
    expect(document.querySelector('code')).toHaveTextContent('craft_look');
  });
});

describe('ToolcallBlockView', () => {
  it('redacts secret args in the detail view', async () => {
    const user = userEvent.setup();
    render(
      <ToolcallBlockView block={BLOCK} sessionId="s1" docId="d1" verifyAvailable={{}} onVerifyCommand={() => {}} />,
    );
    await user.click(screen.getByRole('button', { name: /craft_look/i }));
    expect(screen.getByText(/\[redacted\]/)).toBeInTheDocument();
    expect(screen.queryByText(/sk-should-not-show/)).not.toBeInTheDocument();
  });

  it('falls back to chat command when verify endpoint is missing', async () => {
    const user = userEvent.setup();
    const onVerifyCommand = vi.fn();
    render(
      <ToolcallBlockView
        block={BLOCK}
        sessionId="s1"
        docId="d1"
        verifyAvailable={{ snapshot: false }}
        onVerifyCommand={onVerifyCommand}
      />,
    );
    await user.click(screen.getByRole('button', { name: /craft_look/i }));
    await user.click(screen.getByRole('button', { name: 'Snapshot' }));
    expect(onVerifyCommand).toHaveBeenCalledWith('/snapshot d1');
  });
});

describe('CrafterChat', () => {
  const base = {
    messages: [] as ChatMessage[],
    streaming: false,
    streamError: null,
    chatEnabled: true,
    sessionId: 's1',
    docId: 'd1',
    profileId: null,
    profileLabel: null,
    teamId: null,
    answeringModel: null,
    selectedModel: null,
    onModelChange: () => {},
    verifyAvailable: {},
    onSend: () => {},
    onCancel: () => {},
    onVerifyCommand: () => {},
  };

  it('renders user/assistant/toolcall blocks and the working pill', () => {
    const messages: ChatMessage[] = [
      { id: 'u1', role: 'user', text: 'resize to 800px' },
      { id: 'a1', role: 'assistant', text: '', blocks: [BLOCK], pending: true },
    ];
    render(<CrafterChat {...base} messages={messages} streaming />);
    expect(screen.getByTestId('msg-user')).toHaveTextContent('resize to 800px');
    expect(screen.getByTestId('toolcall-block')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(/working/i);
  });

  it('sends on Enter and cancels on Escape', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    const onCancel = vi.fn();
    const { rerender } = render(
      <CrafterChat {...base} messages={[]} streaming={false} onSend={onSend} onCancel={onCancel} />,
    );
    const box = screen.getByLabelText('Chat message');
    await user.type(box, 'hello{enter}');
    expect(onSend).toHaveBeenCalledWith('hello', undefined);
    rerender(<CrafterChat {...base} messages={[]} streaming onSend={onSend} onCancel={onCancel} />);
    await user.keyboard('{Escape}');
    expect(onCancel).toHaveBeenCalled();
  });

  it('disables the composer until a file is opened', () => {
    render(<CrafterChat {...base} messages={[]} chatEnabled={false} />);
    expect(screen.getByLabelText('Chat message')).toBeDisabled();
    expect(screen.getByText(/pick an app and drop a file/i)).toBeInTheDocument();
  });
});
