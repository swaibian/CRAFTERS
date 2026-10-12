/**
 * Markdown + toolcall render tests: GFM tables/code render, toolcall blocks
 * show redacted args, verify buttons fall back gracefully. Also covers the
 * stream-reducer → render path: every streamed plan line must appear once.
 */
import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CrafterChat } from './CrafterChat';
import { Markdown } from './Markdown';
import { ToolcallBlockView } from './ToolcallView';
import { useChatStream } from '../hooks/useChatStream';
import type { ChatMessage, ToolCallBlock } from '../lib/chat';

const BLOCK: ToolCallBlock = {
  kind: 'toolcall',
  id: 't1',
  name: 'craft_look',
  args: { doc_id: 'd1', api_key: 'sk-should-not-show' },
  result: { ok: true, summary: 'looked fine' },
  status: 'done',
};

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
  return { ok: true, status: 200, body: stream } as unknown as Response;
}

function sseData(payload: unknown): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

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

  it('renders command_run args compactly: command inline, params on one line', () => {
    render(
      <ToolcallBlockView
        block={{
          kind: 'toolcall',
          id: 't-cmd',
          name: 'command_run',
          args: { command: 'image.imageRotation.90cw', params: { radius: 3 } },
          result: { ok: true, summary: 'command_run ok (revision 1)' },
          status: 'done',
        }}
        sessionId="s1"
        docId="d1"
        verifyAvailable={{}}
        onVerifyCommand={() => {}}
      />,
    );
    // name + command id sit in the head row (long ids wrap, never truncate).
    const head = screen.getByRole('button', { name: /command_run/ });
    expect(head).toHaveTextContent('command_run image.imageRotation.90cw');
    // params render as one compact `key: value` line — not a raw JSON blob.
    const args = screen.getByTestId('toolcall-args');
    expect(args).toHaveTextContent('params: {"radius":3}');
    expect(args.querySelector('pre')).toBeNull();
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

  it('groups reasoning steps and keeps tool calls collapsed by default', () => {
    const message: ChatMessage = {
      id: 'a-steps',
      role: 'assistant',
      text: '',
      blocks: [
        { kind: 'reasoning', id: 'r1', text: 'First reasoning step' },
        { ...BLOCK, id: 't1' },
        { kind: 'reasoning', id: 'r2', text: 'Second reasoning step' },
        { ...BLOCK, id: 't2', name: 'craft_edit' },
        { ...BLOCK, id: 't3', name: 'craft_save' },
        { kind: 'reasoning', id: 'r3', text: 'Third reasoning step' },
        { kind: 'final', id: 'f1', text: 'The image is rotated.' },
      ],
    };
    render(<CrafterChat {...base} messages={[message]} />);

    expect(screen.getByText('Reasoning')).toBeInTheDocument();
    expect(screen.getByText('Tool calls')).toBeInTheDocument();
    expect(screen.getByTestId('final-response')).toHaveTextContent('The image is rotated.');
    expect(screen.getAllByTestId('reasoning-step').map((step) => (step as HTMLDetailsElement).open)).toEqual([
      false,
      true,
      true,
    ]);
    expect((document.querySelector('.toolcall-group') as HTMLDetailsElement).open).toBe(false);
    expect(
      screen.getAllByTestId('toolcall-block').map((block) =>
        block.querySelector('.toolcall-head')?.getAttribute('aria-expanded'),
      ),
    ).toEqual(['false', 'false', 'false']);
  });

  it('renders each streamed plan line exactly once (stream reducer → render)', async () => {
    // SSE sequence mirroring the controller mapping of one live run: agent
    // `plan`/`observe` events arrive as `text.delta` (phase reasoning), tools
    // as tool.call/tool.result, the wrap-up as `text.delta` (phase final).
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          sseData({ event: 'response.started', run_id: 'r1', model: 'm-live', team: null }),
          sseData({ event: 'text.delta', delta: 'Rotating 90° clockwise — checking the command and applying it.\n', phase: 'reasoning' }),
          sseData({ event: 'tool.call', name: 'command_run', args: { command: 'image.imageRotation.90cw' } }),
          sseData({ event: 'tool.result', name: 'command_run', ok: true, summary: 'command_run ok (revision 1)' }),
          sseData({ event: 'text.delta', delta: '[observed revision 1] \n', phase: 'reasoning' }),
          sseData({ event: 'text.delta', delta: 'Rotating 90° clockwise for you.\n', phase: 'reasoning' }),
          sseData({ event: 'tool.call', name: 'command_run', args: { command: 'image.imageRotation.90cw' } }),
          sseData({ event: 'tool.result', name: 'command_run', ok: true, summary: 'command_run ok (revision 2)' }),
          sseData({ event: 'text.delta', delta: '[observed revision 2] \n', phase: 'reasoning' }),
          sseData({ event: 'text.delta', delta: 'Rotated 90° clockwise — wrapping up.\n', phase: 'reasoning' }),
          sseData({ event: 'tool.call', name: 'done', args: { summary: 'Rotated the open document 90° clockwise.' } }),
          sseData({ event: 'tool.result', name: 'done', ok: true, summary: 'done ok' }),
          sseData({ event: 'text.delta', delta: 'Rotated the open document 90° clockwise.', phase: 'final' }),
          sseData({ event: 'response.completed', message_id: 'r1' }),
        ]),
      ),
    );
    const messages: ChatMessage[] = [];
    const { result } = renderHook(() =>
      useChatStream(
        (m) => messages.push(m),
        (id, patch) => {
          const i = messages.findIndex((m) => m.id === id);
          if (i >= 0) messages[i] = patch(messages[i]!);
        },
      ),
    );
    await act(async () => {
      result.current.send({ session_id: 's1', message: 'rotate' }, 'rotate');
      await new Promise((r) => setTimeout(r, 50));
    });

    const assistant = messages.find((m) => m.role === 'assistant')!;
    // The reducer folds each plan/observe delta exactly once (annotation +
    // narration merge into one step, never duplicated).
    expect(
      (assistant.blocks ?? []).filter((b) => b.kind === 'reasoning').map((b) => (b as { text: string }).text),
    ).toEqual([
      'Rotating 90° clockwise — checking the command and applying it.\n',
      '[observed revision 1] \nRotating 90° clockwise for you.\n',
      '[observed revision 2] \nRotated 90° clockwise — wrapping up.\n',
    ]);

    render(<CrafterChat {...base} messages={[assistant]} />);
    const thread = document.querySelector('.reasoning-group')!.textContent ?? '';
    for (const piece of [
      'Rotating 90° clockwise — checking the command and applying it.',
      '[observed revision 1]',
      'Rotating 90° clockwise for you.',
      '[observed revision 2]',
      'Rotated 90° clockwise — wrapping up.',
    ]) {
      expect(thread.split(piece).length - 1, `expected exactly one copy of: ${piece}`).toBe(1);
    }
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
