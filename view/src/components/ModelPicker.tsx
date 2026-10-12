/**
 * ModelPicker — small icon button that opens a model search modal.
 *
 * Why: profiles can expose dozens of model ids (OpenRouter list spilling
 * down the screen from a native <select>). A modal with a search field
 * scales: the button shows the current pick truncated, the modal offers
 * type-to-filter + ArrowUp/Down + Enter, Esc/backdrop to close. No key
 * material ever rendered.
 */

import { useEffect, useId, useRef, useState } from 'react';

export function ModelPicker({
  models,
  selected,
  activeProfileDefaultModel,
  disabled,
  loading,
  noProfile,
  onChange,
}: {
  models: string[];
  selected: string | null;
  /** Effective profile default (shown when no override is picked). */
  activeProfileDefaultModel?: string | null;
  disabled: boolean;
  loading: boolean;
  noProfile: boolean;
  onChange?: (model: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [highlight, setHighlight] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const q = query.trim().toLowerCase();
  const filtered = q ? models.filter((m) => m.toLowerCase().includes(q)) : models;
  const defaultLabel = activeProfileDefaultModel || 'profile default';
  // Profile-default row only when the query is empty or matches it —
  // otherwise a nonsense query would never reach the empty state.
  const showDefault = !noProfile && (q === '' || defaultLabel.toLowerCase().includes(q));
  const rows: (string | null)[] = [...(showDefault ? [null as null] : []), ...filtered];

  useEffect(() => {
    setHighlight(0);
  }, [q, models.length]);

  // Focus search on open.
  useEffect(() => {
    if (open) {
      setQuery('');
      setHighlight(0);
      const t = window.setTimeout(() => searchRef.current?.focus(), 0);
      return () => window.clearTimeout(t);
    }
    return undefined;
  }, [open ]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open ]);

  const current = noProfile ? 'mock brain' : (selected ?? defaultLabel);
  const buttonTitle = noProfile
    ? 'mock brain — pick a profile in Settings'
    : loading && models.length === 0
      ? 'Loading models…'
      : `Model: ${current} — choose`;

  function pick(model: string | null) {
    onChange?.(model);
    setOpen(false);
  }

  function onSearchKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, rows.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      if (rows.length > 0) {
        e.preventDefault();
        pick(rows[highlight] ?? null);
      }
    }
  }

  return (
    <div className="model-picker">
      <button
        type="button"
        className={`model-picker-button${selected && !noProfile ? ' custom' : ''}`}
        data-testid="model-picker-button"
        aria-label="Choose model"
        title={buttonTitle}
        aria-haspopup="dialog"
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        <span aria-hidden="true">🤖</span>
        <span className="model-picker-label" data-testid="model-current">
          {loading && models.length === 0 && !noProfile ? '…' : current}
        </span>
        {models.length > 0 && (
          <span className="muted tiny" data-testid="model-count" title={`${models.length} models available`}>
            {models.length} models
          </span>
        )}
      </button>
      {open && (
        <div
          className="model-modal-backdrop"
          data-testid="model-picker-modal"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div role="dialog" aria-modal="true" aria-label="Choose model" className="model-modal">
            <div className="model-modal-head">
              <strong>Choose model</strong>
              <button type="button" aria-label="Close model picker" onClick={() => setOpen(false)}>
                ✕
              </button>
            </div>
            <input
              ref={searchRef}
              aria-label="Search models"
              placeholder="Search models…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onSearchKeyDown}
            />
            <p className="muted tiny" role="status">
              {filtered.length} of {models.length} shown
            </p>
            <ul id={listId} role="listbox" aria-label="Models" className="model-modal-list">
              {rows.length === 0 && (
                <li className="muted tiny" data-testid="model-empty">
                  No models match “{query.trim()}”.
                </li>
              )}
              {rows.map((m, i) => (
                <li
                  key={m ?? '__default__'}
                  role="option"
                  aria-selected={(selected ?? null) === m}
                  data-testid={m === null ? 'model-option-default' : undefined}
                  className={`model-modal-option${i === highlight ? ' highlighted' : ''}${
                    (selected ?? null) === m ? ' selected' : ''
                  }`}
                  onMouseEnter={() => setHighlight(i)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    pick(m);
                  }}
                >
                  {m ?? defaultLabel}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
