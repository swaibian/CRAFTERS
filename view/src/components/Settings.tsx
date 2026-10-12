/**
 * Settings (TC-B-02) — THE SETUP VIEW.
 *
 * Why (stories #4–#6): unblocks the agent brain with the user's own
 * endpoint+key. "AI Endpoints + Keys": profile list, add/edit form (label,
 * api_base URL, api_key password input, default model, Test-connection
 * button), active-profile radio, Scaico key + team select from /api/teams
 * (no key → mailto CTA contact@swaibian.com), gateway endpoint field.
 * Keys render masked only, never touch logs/localStorage (sessionStorage
 * holds the active id only).
 */

import { useEffect, useState } from 'react';
import {
  ApiError,
  createProfile,
  deleteProfile,
  fetchProfileModels,
  fetchProfiles,
  fetchSettingsActive,
  fetchTeams,
  saveGatewayEndpoint,
  saveScaicoKey,
  selectTeam,
  setActiveProfile,
  testProfileConnection,
  updateProfile,
  type ProfilePayload,
  type SettingsProfile,
  type TeamInfo,
} from '../lib/api';
import { logger } from '../lib/logger';

const ACTIVE_ID_KEY = 'crafter.activeProfileId';
const GATEWAY_KEY = 'crafter.gatewayEndpoint';

const EMPTY_FORM: ProfilePayload = { label: '', api_base: '', api_key: '', default_model: '' };

export function Settings() {
  const [profiles, setProfiles] = useState<SettingsProfile[]>([]);
  const [activeId, setActiveId] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem(ACTIVE_ID_KEY);
    } catch {
      return null;
    }
  });
  const [form, setForm] = useState<ProfilePayload>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [teams, setTeams] = useState<TeamInfo[]>([]);
  const [teamId, setTeamId] = useState<string>('');
  const [gateway, setGateway] = useState<string>(() => {
    try {
      return sessionStorage.getItem(GATEWAY_KEY) ?? 'http://127.0.0.1:8790';
    } catch {
      return 'http://127.0.0.1:8790';
    }
  });
  const [scaicoKey, setScaicoKey] = useState('');
  const [scaicoMasked, setScaicoMasked] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [unreachable, setUnreachable] = useState(false);
  // Model ids fetched after a successful Test-connection (dropdown source).
  const [testedModels, setTestedModels] = useState<string[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchProfiles();
        setProfiles(data.profiles);
        if (data.active_profile_id) {
          setActiveId(data.active_profile_id);
          try {
            sessionStorage.setItem(ACTIVE_ID_KEY, data.active_profile_id);
          } catch {
            /* storage unavailable — ignore */
          }
        }
      } catch (err) {
        if (err instanceof ApiError && err.unreachable) setUnreachable(true);
        else setError(err instanceof Error ? err.message : 'Could not load profiles');
      }
      try {
        setTeams(await fetchTeams());
      } catch (err) {
        if (err instanceof ApiError && err.unreachable) setUnreachable(true);
        // teams failing must not hide the profile form
      }
      try {
        const active = await fetchSettingsActive();
        if (active.selected_team_id) setTeamId(active.selected_team_id);
        if (active.gateway_endpoint) {
          setGateway(active.gateway_endpoint);
          try {
            sessionStorage.setItem(GATEWAY_KEY, active.gateway_endpoint);
          } catch {
            /* storage unavailable — ignore */
          }
        }
        if (active.scaico.api_key_masked) setScaicoMasked(active.scaico.api_key_masked);
      } catch {
        // active-settings failing must not hide anything (best-effort sync)
      }
    })();
  }, []);

  function setField<K extends keyof ProfilePayload>(k: K, v: string) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function handleSave() {
    setError(null);
    setStatus(null);
    if (!form.label.trim() || !form.api_base.trim()) {
      setError('Label and API base URL are required.');
      return;
    }
    try {
      if (editingId) {
        const payload: Partial<ProfilePayload> = {
          label: form.label,
          api_base: form.api_base,
          default_model: form.default_model,
        };
        if (form.api_key) payload.api_key = form.api_key; // empty = keep server-side key
        const updated = await updateProfile(editingId, payload);
        setProfiles((ps) => ps.map((p) => (p.id === editingId ? updated : p)));
        setStatus(`Saved “${updated.label}”.`);
      } else {
        if (!form.api_key) {
          setError('API key is required for a new profile.');
          return;
        }
        const created = await createProfile(form);
        setProfiles((ps) => [...ps, created]);
        setStatus(`Added “${created.label}”.`);
      }
      setForm(EMPTY_FORM);
      setEditingId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    }
  }

  async function handleTest() {
    setTesting(true);
    setStatus(null);
    setError(null);
    try {
      const res = await testProfileConnection(form);
      setStatus(res.ok ? `Connection ok: ${res.message}` : `Connection failed: ${res.message}`);
      logger.info('settings.profile.tested', { ok: res.ok });
      if (res.ok) {
        // Fetch model ids for the edited profile (saved id when editing) so
        // the default-model dropdown offers real options. Failure/offline
        // keeps the free-text input — never blocks the form.
        const targetId = editingId;
        if (targetId) {
          try {
            const data = await fetchProfileModels(targetId);
            setTestedModels(data.models.map((m) => m.id));
          } catch {
            setTestedModels([]);
          }
        } else {
          setTestedModels([]);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Test failed');
    } finally {
      setTesting(false);
    }
  }

  async function handleActivate(id: string) {
    setActiveId(id);
    try {
      sessionStorage.setItem(ACTIVE_ID_KEY, id);
    } catch {
      /* ignore */
    }
    try {
      await setActiveProfile(id);
      setStatus('Active profile saved server-side.');
    } catch {
      setStatus('Active profile selected locally (server unreachable).');
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteProfile(id);
      setProfiles((ps) => ps.filter((p) => p.id !== id));
      if (activeId === id) {
        setActiveId(null);
        try {
          sessionStorage.removeItem(ACTIVE_ID_KEY);
        } catch {
          /* ignore */
        }
        try {
          await setActiveProfile(null);
        } catch {
          /* server best-effort */
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    }
  }

  async function handleTeamSelect(id: string) {
    setTeamId(id);
    try {
      await selectTeam(id || null);
      setStatus(id ? 'Team selected for agent runs.' : 'Team cleared.');
    } catch {
      setStatus('Team selected locally (server unreachable).');
    }
  }

  async function handleScaicoSave() {
    setError(null);
    try {
      const res = await saveScaicoKey(scaicoKey);
      setScaicoMasked(res.api_key_masked);
      setScaicoKey('');
      setStatus('Scaico key saved server-side (masked).');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scaico save failed');
    }
  }

  async function saveGateway() {
    try {
      sessionStorage.setItem(GATEWAY_KEY, gateway);
    } catch {
      /* ignore */
    }
    try {
      const res = await saveGatewayEndpoint(gateway);
      setGateway(res.gateway_endpoint);
      setStatus('Gateway endpoint saved server-side.');
    } catch {
      setStatus('Gateway endpoint saved for this session (server unreachable).');
    }
    logger.info('settings.gateway.saved', {});
  }

  return (
    <div className="settings" data-testid="settings-view">
      <h2>AI Endpoints + Keys</h2>
      {unreachable && (
        <p className="notice" role="status">
          Controller unreachable — settings are read-only mock data until the controller (:8790) is
          up. Nothing here will crash; retry later.
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {status && (
        <p className="ok" role="status">
          {status}
        </p>
      )}

      <section aria-label="Endpoint profiles">
        <h3>Profiles</h3>
        {profiles.length === 0 && <p className="muted">No profiles yet — add your endpoint below.</p>}
        <ul className="profile-list">
          {profiles.map((p) => (
            <li key={p.id} data-testid="profile-row">
              <label>
                <input
                  type="radio"
                  name="active-profile"
                  checked={activeId === p.id}
                  onChange={() => void handleActivate(p.id)}
                  aria-label={`Use ${p.label} as active profile`}
                />
                <strong>{p.label}</strong>
              </label>
              <span className="muted">{p.api_base}</span>
              <span className="muted" data-testid="masked-key">
                key: {p.api_key_masked}
              </span>
              <span className="muted">model: {p.default_model}</span>
              <button
                type="button"
                onClick={() => {
                  setEditingId(p.id);
                  setForm({ label: p.label, api_base: p.api_base, api_key: '', default_model: p.default_model });
                }}
              >
                Edit
              </button>
              <button type="button" onClick={() => void handleDelete(p.id)}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label={editingId ? 'Edit profile' : 'Add profile'}>
        <h3>{editingId ? 'Edit profile' : 'Add profile'}</h3>
        <div className="form-grid">
          <label>
            Label
            <input aria-label="Profile label" value={form.label} onChange={(e) => setField('label', e.target.value)} />
          </label>
          <label>
            API base URL
            <input
              aria-label="API base URL"
              inputMode="url"
              placeholder="https://…"
              value={form.api_base}
              onChange={(e) => setField('api_base', e.target.value)}
            />
          </label>
          <label>
            API key
            <input
              aria-label="API key"
              type="password"
              autoComplete="new-password"
              placeholder={editingId ? '(unchanged)' : 'sk-…'}
              value={form.api_key}
              onChange={(e) => setField('api_key', e.target.value)}
            />
          </label>
          <label>
            Default model
            {testedModels.length > 0 ? (
              <select
                aria-label="Default model"
                value={form.default_model}
                onChange={(e) => setField('default_model', e.target.value)}
              >
                <option value="">Select a model…</option>
                {testedModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            ) : (
              <input
                aria-label="Default model"
                value={form.default_model}
                onChange={(e) => setField('default_model', e.target.value)}
              />
            )}
          </label>
        </div>
        <div className="row">
          <button type="button" onClick={() => void handleTest()} disabled={testing}>
            {testing ? 'Testing…' : 'Test connection'}
          </button>
          <button type="button" onClick={() => void handleSave()}>
            {editingId ? 'Save changes' : 'Add profile'}
          </button>
          {editingId && (
            <button
              type="button"
              onClick={() => {
                setEditingId(null);
                setForm(EMPTY_FORM);
              }}
            >
              Cancel
            </button>
          )}
        </div>
      </section>

      <section aria-label="Scaico team">
        <h3>Scaico team</h3>
        <div className="form-grid">
          <label>
            Scaico API key
            <input
              aria-label="Scaico API key"
              type="password"
              autoComplete="new-password"
              placeholder={scaicoMasked ? `(saved: ${scaicoMasked})` : 'scaico-…'}
              value={scaicoKey}
              onChange={(e) => setScaicoKey(e.target.value)}
            />
          </label>
        </div>
        <div className="row">
          <button type="button" onClick={() => void handleScaicoSave()} disabled={!scaicoKey}>
            Save Scaico key
          </button>
        </div>
        {teams.length === 0 ? (
          <p>
            No Scaico access yet?{' '}
            <a href="mailto:contact@swaibian.com?subject=Scaico%20access%20for%20Crafter">
              Request access via contact@swaibian.com
            </a>
          </p>
        ) : (
          <label>
            Team
            <select aria-label="Scaico team" value={teamId} onChange={(e) => void handleTeamSelect(e.target.value)}>
              <option value="">Select a team…</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.agents.length} agents)
                </option>
              ))}
            </select>
          </label>
        )}
      </section>

      <section aria-label="Gateway endpoint">
        <h3>Gateway endpoint</h3>
        <label>
          Controller URL
          <input aria-label="Gateway endpoint" value={gateway} onChange={(e) => setGateway(e.target.value)} />
        </label>
        <button type="button" onClick={saveGateway}>
          Save endpoint
        </button>
      </section>
    </div>
  );
}
