/**
 * Dropzone tests: drop → POST /api/files/open → opened-file header;
 * graceful error when the controller is down.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { Dropzone } from './Dropzone';

const OPENED = {
  doc_id: 'd1',
  app: 'photocraft',
  name: 'photo.psd',
  session_id: 's1',
  inspect: { width: 800, height: 600, mode: 'RGB' },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

function dropFile(el: Element, file: File) {
  const dataTransfer = { files: [file] } as unknown as DataTransfer;
  const event = new Event('drop', { bubbles: true }) as Event & { dataTransfer?: DataTransfer };
  event.dataTransfer = dataTransfer;
  el.dispatchEvent(event);
}

describe('Dropzone', () => {
  it('opens a dropped file and shows the header with inspect summary', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => OPENED }),
    );
    const onOpened = vi.fn();
    render(<Dropzone app="photocraft" opened={null} onOpened={onOpened} />);
    dropFile(screen.getByRole('button', { name: /drop a file/i }), new File(['x'], 'photo.psd'));
    await waitFor(() => expect(onOpened).toHaveBeenCalledOnce());
    // openFile maps the controller payload (kind→app etc.) and fills the
    // session-scoped thumbnail URL.
    expect(onOpened.mock.calls[0]?.[0]).toMatchObject({ ...OPENED, thumbnail_url: expect.stringContaining('/api/files/d1/thumbnail') });
    const [[body]] = (fetch as unknown as { mock: { calls: [RequestInfo, RequestInit?][] } }).mock.calls;
    expect(String(body)).toBe('/api/files/open');
  });

  it('renders the opened-file header once a file is open', () => {
    render(<Dropzone app="photocraft" opened={OPENED} onOpened={() => {}} />);
    expect(screen.getByTestId('opened-file-header')).toHaveTextContent('photo.psd');
    expect(screen.getByTestId('opened-file-header')).toHaveTextContent('width: 800');
  });

  it('shows an inline error (no crash) when the controller is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('down')));
    render(<Dropzone app="photocraft" opened={null} onOpened={() => {}} />);
    dropFile(screen.getByRole('button', { name: /drop a file/i }), new File(['x'], 'a.psd'));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/controller unreachable/i),
    );
  });

  it('asks to pick an app first when none is armed', async () => {
    const onOpened = vi.fn();
    render(<Dropzone app={null} opened={null} onOpened={onOpened} />);
    dropFile(screen.getByRole('button', { name: /pick an app/i }), new File(['x'], 'a.psd'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/pick an app/i));
    expect(onOpened).not.toHaveBeenCalled();
  });
});
