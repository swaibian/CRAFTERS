/**
 * ToolPicker tests: selection arms the dropzone; pilot apps enabled, rest
 * disabled "soon".
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ToolPicker } from './ToolPicker';

describe('ToolPicker', () => {
  it('selects a pilot app on click', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ToolPicker selected={null} onSelect={onSelect} />);
    await user.click(screen.getByRole('radio', { name: /photocraft/i }));
    expect(onSelect).toHaveBeenCalledWith('photocraft');
  });

  it('marks the selected app checked', () => {
    render(<ToolPicker selected="pdfcraft" onSelect={() => {}} />);
    expect(screen.getByRole('radio', { name: /pdfcraft/i })).toHaveAttribute('aria-checked', 'true');
  });

  it('disables non-pilot apps as soon', () => {
    render(<ToolPicker selected={null} onSelect={() => {}} />);
    const vector = screen.getByRole('radio', { name: /vectorcraft/i });
    expect(vector).toBeDisabled();
    expect(vector).toHaveAttribute('title', expect.stringContaining('soon'));
  });
});
