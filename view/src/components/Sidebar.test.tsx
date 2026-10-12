/**
 * Sidebar tests (mocked fetch): grouping headers per app, New chat resets
 * state, resume loads history + rebinds the file, delete removes the item
 * with an inline confirm, and session_id flows into openFile/stream bodies
 * (covered via api tests + App wiring).
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { groupConversations, relativeTime, Sidebar } from './Sidebar';
import type { ConversationSummary } from '../lib/api';

afterEach(() => {
  vi.unstubAllGlobals();
});

const CONVS: ConversationSummary[] = [
  { id: 'c1', app: 'photocraft', title: 'Photo edit', updated_at: new Date(Date.now() - 5 * 60000).toISOString(), message_count: 4, doc_ids: ['d1'] },
  { id: 'c2', app: 'gridcraft', title: 'Sheet fix', updated_at: new Date(Date.now() - 2 * 3600000).toISOString(), message_count: 2, doc_ids: [] },
  { id: 'c3', title: 'Mystery', updated_at: new Date(Date.now() - 3 * 86400000).toISOString(), message_count: 1, doc_ids: [] },
];

function stubSidebar() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (url: string) => {
      if (String(url).includes('/api/conversations') && !String(url).includes('/api/conversations/'))
        return { ok: true, json: async () => ({ conversations: CONVS }) };
      if (String(url).includes('/api/chat/history'))
        return { ok: true, json: async () => ({ messages: [{ role: 'user', text: 'hi' }] }) };
      if (String(url).includes('/api/files/d1'))
        return {
          ok: true,
          json: async () => ({ doc_id: 'd1', app: 'photocraft', name: 'a.png', session_id: 'c1', inspect: {} }),
        };
      if (String(url).includes('/api/conversations/c2')) return { ok: true, json: async () => ({ deleted: 'c2' }) };
      return { ok: false, status: 404 };
    }),
  );
}

describe('groupConversations', () => {
  it('groups by app with unknown apps under other-unknown', () => {
    const groups = groupConversations(CONVS);
    expect([...groups.keys()]).toEqual(['photocraft', 'gridcraft', 'other-unknown']);
    expect(groups.get('photocraft')).toHaveLength(1);
    expect(groups.get('other-unknown')).toHaveLength(1);
  });

  it('formats relative times', () => {
    const now = Date.parse('2026-01-10T12:00:00Z');
    expect(relativeTime('2026-01-10T11:55:00Z', now)).toBe('5m ago');
    expect(relativeTime('2026-01-10T10:00:00Z', now)).toBe('2h ago');
    expect(relativeTime('2026-01-08T12:00:00Z', now)).toBe('2d ago');
  });
});

describe('Sidebar', () => {
  it('renders grouping headers with titles, times, counts and doc badges', async () => {
    stubSidebar();
    render(<Sidebar activeSessionId={null} onNewChat={() => {}} onResume={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('group-photocraft')).toBeInTheDocument());
    expect(screen.getByTestId('group-gridcraft')).toBeInTheDocument();
    expect(screen.getByTestId('group-other-unknown')).toBeInTheDocument();
    expect(screen.getByText('Photo edit')).toBeInTheDocument();
    expect(screen.getByText(/5m ago/)).toBeInTheDocument();
    expect(screen.getByText(/4 msgs/)).toBeInTheDocument();
    expect(screen.getAllByTestId('conversation-item')).toHaveLength(3);
  });

  it('New chat calls the reset handler', async () => {
    stubSidebar();
    const onNewChat = vi.fn();
    render(<Sidebar activeSessionId={null} onNewChat={onNewChat} onResume={() => {}} />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'New chat' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'New chat' }));
    expect(onNewChat).toHaveBeenCalledOnce();
  });

  it('resume loads history and rebinds the opened file', async () => {
    stubSidebar();
    const user = userEvent.setup();
    const onResume = vi.fn();
    render(<Sidebar activeSessionId={null} onNewChat={() => {}} onResume={onResume} />);
    await waitFor(() => expect(screen.getByText('Photo edit')).toBeInTheDocument());
    await user.click(screen.getByText('Photo edit'));
    await waitFor(() => expect(onResume).toHaveBeenCalledOnce());
    const [sessionId, messages, opened] = onResume.mock.calls[0] as [string, { text: string }[], { doc_id: string } | null];
    expect(sessionId).toBe('c1');
    expect(messages[0]).toMatchObject({ text: 'hi' });
    expect(opened).toMatchObject({ doc_id: 'd1' });
    const urls = (fetch as unknown as { mock: { calls: [string][] } }).mock.calls.map((c) => c[0]);
    expect(urls.some((u) => u.includes('/api/chat/history?session_id=c1'))).toBe(true);
    expect(urls.some((u) => u.includes('/api/files/d1?session_id=c1'))).toBe(true);
  });

  it('resume without docs passes a null opened file', async () => {
    stubSidebar();
    const user = userEvent.setup();
    const onResume = vi.fn();
    render(<Sidebar activeSessionId={null} onNewChat={() => {}} onResume={onResume} />);
    await waitFor(() => expect(screen.getByText('Sheet fix')).toBeInTheDocument());
    await user.click(screen.getByText('Sheet fix'));
    await waitFor(() => expect(onResume).toHaveBeenCalledOnce());
    expect(onResume.mock.calls[0]?.[2]).toBeNull();
  });

  it('delete uses an inline confirm and removes the item', async () => {
    stubSidebar();
    const user = userEvent.setup();
    render(<Sidebar activeSessionId={null} onNewChat={() => {}} onResume={() => {}} />);
    await waitFor(() => expect(screen.getByText('Sheet fix')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Delete Sheet fix' }));
    await user.click(screen.getByRole('button', { name: 'Confirm delete Sheet fix' }));
    await waitFor(() => expect(screen.queryByText('Sheet fix')).not.toBeInTheDocument());
    expect(screen.getByText('Photo edit')).toBeInTheDocument();
  });
});
