/**
 * Typed controller client (contract: controller FastAPI :8790, built in parallel).
 *
 * Why (SW-REQ-CHAT / SW-REQ-STREAM): every view feature — teams, settings
 * profiles, file-open, SSE chat stream, verify actions — talks to the
 * controller through this module, so unreachable-controller degradation lives
 * in exactly one place. All failures surface as {@link ApiError} with
 * `unreachable: true` when the network itself failed; callers show the mock
 * fallback notice instead of crashing.
 */

import { logger } from './logger';

export class ApiError extends Error {
  readonly status: number;
  readonly unreachable: boolean;
  constructor(message: string, opts: { status?: number; unreachable?: boolean } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = opts.status ?? 0;
    this.unreachable = opts.unreachable ?? false;
  }
}

// --- Types (mirror controller contract) ---

export interface AgentInfo {
  id: string;
  name: string;
}

export interface TeamInfo {
  id: string;
  name: string;
  agents: AgentInfo[];
}

export interface SettingsProfile {
  id: string;
  label: string;
  api_base: string;
  /** Masked server-side (e.g. "sk-...4f2a"); never the full key. */
  api_key_masked: string;
  default_model: string;
}

export interface ProfilePayload {
  label: string;
  api_base: string;
  api_key: string;
  default_model: string;
}

export interface OpenedFile {
  doc_id: string;
  app: string;
  name: string;
  session_id: string;
  inspect: Record<string, unknown>;
  thumbnail_url?: string;
  /** "upload" (dropped file) or "live" (captured from a running desktop app). */
  source?: string;
  /** Desktop app the open document lives in (source === "live" only). */
  live_app?: string;
  /** Engine document index of the open doc (attach only; file-info omits it). */
  live_index?: number;
}

export interface ChatStreamRequest {
  session_id: string;
  doc_id?: string;
  message: string;
  profile_id?: string;
  team_id?: string;
  /** Optional model override; unknown model → 400 from the controller. */
  model?: string;
}

/** SSE events per send_task_stream contract. */
export type StreamEvent =
  | { type: 'response.started'; run_id: string; model: string; team: string | null }
  | { type: 'text.delta'; delta: string; phase?: 'reasoning' | 'final' }
  | { type: 'tool.call'; name: string; args: Record<string, unknown> }
  | { type: 'tool.result'; name: string; ok: boolean; summary: string }
  | { type: 'response.completed'; message_id: string }
  | { type: 'response.error'; message: string };

export interface VerifyAction {
  id: 'snapshot' | 'restore' | 'record-view';
  label: string;
  endpoint: string;
}

// --- Low-level fetch ---

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    logger.warn('api.unreachable', { path });
    throw new ApiError(`Controller unreachable at ${path}`, { unreachable: true, status: 0 });
  }
  if (!res.ok) {
    logger.warn('api.http-error', { path, status: res.status });
    throw new ApiError(`Request failed: ${path} (${res.status})`, { status: res.status });
  }
  return (await res.json()) as T;
}

// --- Teams ---

export async function fetchTeams(): Promise<TeamInfo[]> {
  const data = await request<{ teams: TeamInfo[] }>('/api/teams');
  return data.teams ?? [];
}

// --- Settings profiles ---

export async function fetchProfiles(): Promise<{ profiles: SettingsProfile[]; active_profile_id: string | null }> {
  const data = await request<{ profiles: SettingsProfile[]; active_profile_id?: string | null }>(
    '/api/settings/profiles',
  );
  // Newer controllers include active_profile_id inline; older ones only
  // expose it via GET /api/settings/active — merge best-effort, never fail
  // the profile list when the active endpoint is down.
  if (data.active_profile_id !== undefined) {
    return { profiles: data.profiles ?? [], active_profile_id: data.active_profile_id };
  }
  try {
    const active = await fetchSettingsActive();
    return { profiles: data.profiles ?? [], active_profile_id: active.active_profile_id };
  } catch {
    return { profiles: data.profiles ?? [], active_profile_id: null };
  }
}

function unwrapProfile(data: unknown): SettingsProfile {
  if (data && typeof data === 'object' && 'profile' in (data as Record<string, unknown>)) {
    return (data as { profile: SettingsProfile }).profile;
  }
  return data as SettingsProfile;
}

export async function createProfile(payload: ProfilePayload): Promise<SettingsProfile> {
  logger.info('api.profile.create', { label: payload.label, api_base: payload.api_base });
  const data = await request<SettingsProfile | { profile: SettingsProfile }>('/api/settings/profiles', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return unwrapProfile(data);
}

export async function updateProfile(
  id: string,
  payload: Partial<ProfilePayload> & { active_profile_id?: string },
): Promise<SettingsProfile> {
  logger.info('api.profile.update', { id });
  const data = await request<SettingsProfile | { profile: SettingsProfile }>(`/api/settings/profiles/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
  return unwrapProfile(data);
}

export async function deleteProfile(id: string): Promise<void> {
  logger.info('api.profile.delete', { id });
  await request(`/api/settings/profiles/${id}`, { method: 'DELETE' });
}

export async function testProfileConnection(payload: ProfilePayload): Promise<{ ok: boolean; message: string }> {
  logger.info('api.profile.test', { api_base: payload.api_base });
  const data = await request<Record<string, unknown>>('/api/settings/profiles/test', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  // The controller answers {ok, reachable/auth/models…} or {ok:false, error};
  // normalize to the {ok, message} shape the Settings form renders.
  const message = String(
    data.message ?? data.error ?? (data.ok ? 'reachable' : 'connection failed'),
  );
  return { ok: Boolean(data.ok), message };
}

export interface ProfileModel {
  id: string;
}

/**
 * List models for a profile (GET /api/settings/profiles/models?profile_id=ID).
 * Why (model picker): populates the Settings default-model dropdown and the
 * chat composer select. 404 = unknown profile, 502 = endpoint failure.
 */
export async function fetchProfileModels(profile_id: string): Promise<{ models: ProfileModel[]; cached: boolean }> {
  const data = await request<{ models: ProfileModel[]; cached: boolean }>(
    `/api/settings/profiles/models?profile_id=${encodeURIComponent(profile_id)}`,
  );
  return { models: data.models ?? [], cached: data.cached };
}

export async function fetchSettingsActive(): Promise<{
  active_profile_id: string | null;
  mock: boolean;
  gateway_endpoint: string;
  scaico: { has_key: boolean; api_key_masked: string; mailto: string };
  selected_team_id: string | null;
}> {
  return request('/api/settings/active');
}

export async function setActiveProfile(profile_id: string | null): Promise<void> {
  logger.info('api.profile.activate', {});
  await request('/api/settings/active', { method: 'PUT', body: JSON.stringify({ profile_id }) });
}

export async function saveScaicoKey(api_key: string): Promise<{ has_key: string; api_key_masked: string }> {
  logger.info('api.scaico.save', {});
  return request('/api/settings/scaico-key', { method: 'PUT', body: JSON.stringify({ api_key }) });
}

export async function selectTeam(team_id: string | null): Promise<{ selected_team_id: string | null }> {
  logger.info('api.team.select', {});
  return request('/api/settings/team', { method: 'PUT', body: JSON.stringify({ team_id }) });
}

export async function saveGatewayEndpoint(endpoint: string): Promise<{ gateway_endpoint: string }> {
  logger.info('api.gateway.save', {});
  return request('/api/settings/gateway', { method: 'PUT', body: JSON.stringify({ endpoint }) });
}

// --- Files ---

/**
 * Map a controller file payload to the view OpenedFile shape.
 * Accepts both the legacy view shape ({app, name, session_id}) and the
 * controller shape ({kind, source_name}); kind→app, source_name→name.
 */
function toOpenedFile(data: Record<string, unknown>, fallbackSession: string): OpenedFile {
  const docId = String(data.doc_id ?? '');
  const sessionId = String(data.session_id ?? fallbackSession);
  return {
    doc_id: docId,
    app: String(data.app ?? data.kind ?? ''),
    name: String(data.name ?? data.source_name ?? data.filename ?? docId),
    session_id: sessionId,
    inspect: (data.inspect as Record<string, unknown>) ?? {},
    thumbnail_url:
      (data.thumbnail_url as string | undefined) ??
      `/api/files/${encodeURIComponent(docId)}/thumbnail?session_id=${encodeURIComponent(sessionId)}`,
    source: (data.source as string | undefined) ?? 'upload',
    live_app: data.live_app as string | undefined,
    live_index: typeof data.live_index === 'number' ? data.live_index : undefined,
  };
}
export async function openFile(file: File, app: string, session_id?: string): Promise<OpenedFile> {
  const form = new FormData();
  form.append('file', file);
  form.append('app', app);
  // Server defaults to "default" when absent — keep backward compat.
  if (session_id) form.append('session_id', session_id);
  let res: Response;
  try {
    res = await fetch('/api/files/open', { method: 'POST', body: form });
  } catch {
    logger.warn('api.unreachable', { path: '/api/files/open' });
    throw new ApiError('Controller unreachable at /api/files/open', { unreachable: true, status: 0 });
  }
  if (!res.ok) {
    logger.warn('api.http-error', { path: '/api/files/open', status: res.status });
    throw new ApiError(`File open failed (${res.status})`, { status: res.status });
  }
  const data = (await res.json()) as Record<string, unknown>;
  const opened = toOpenedFile(data, session_id ?? 'default');
  logger.info('api.file.opened', { app, name: file.name, doc_id: opened.doc_id });
  return opened;
}

/**
 * Rebind an already-opened document into a session (GET /api/files/{doc_id}).
 * Why (sidebar resume): restoring a conversation re-attaches its file so the
 * thread header + download link work without re-uploading.
 */
export async function fetchOpenedFile(doc_id: string, session_id?: string): Promise<OpenedFile> {
  const qs = session_id ? `?session_id=${encodeURIComponent(session_id)}` : '';
  const data = await request<Record<string, unknown>>(`/api/files/${encodeURIComponent(doc_id)}${qs}`);
  return toOpenedFile(data, session_id ?? 'default');
}

export function thumbnailUrl(docId: string, sessionId?: string): string {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  return `/api/files/${encodeURIComponent(docId)}/thumbnail${qs}`;
}

export function downloadResultUrl(docId: string, sessionId?: string): string {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  return `/api/files/${encodeURIComponent(docId)}/download${qs}`;
}

// --- Live desktop apps (started with --control) ---

export interface LiveAppStatus {
  app: string;
  running: boolean;
  mode: string;
  /** TCP apps the Launch button may start (pdfcraft stays manual). */
  launchable?: boolean;
  last_error?: string;
  hint?: string;
}

export interface LiveDocument {
  index: number;
  name: string;
  width?: number | null;
  height?: number | null;
  dirty: boolean;
  active: boolean;
}

/**
 * Probe every live-app control channel (GET /api/live/status).
 * Never rejects on app-down — down apps come back as running:false.
 */
export async function fetchLiveStatus(): Promise<LiveAppStatus[]> {
  const data = await request<{ apps: LiveAppStatus[] }>('/api/live/status');
  return data.apps ?? [];
}

/**
 * List the documents open in a live window (GET /api/live/documents).
 * 502 = app down (message names the --control command to start it).
 */
export async function fetchLiveDocuments(app: string): Promise<{ active: number | null; documents: LiveDocument[] }> {
  const data = await request<{ active: number | null; documents: LiveDocument[] }>(
    `/api/live/documents?app=${encodeURIComponent(app)}`,
  );
  return { active: data.active ?? null, documents: data.documents ?? [] };
}

/**
 * Start a down desktop app and wait for its control channel
 * (POST /api/live/launch). 409 = not launchable (pdfcraft, file-based —
 * start by hand); 502 = binary missing / still starting (Refresh retries).
 */
export async function launchLiveApp(app: string): Promise<{ app: string; running: boolean; mode: string }> {
  logger.info('api.live.launch', { app });
  let res: Response;
  try {
    res = await fetch('/api/live/launch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app }),
    });
  } catch {
    logger.warn('api.unreachable', { path: '/api/live/launch' });
    throw new ApiError('Controller unreachable at /api/live/launch', { unreachable: true, status: 0 });
  }
  if (!res.ok) {
    logger.warn('api.http-error', { path: '/api/live/launch', status: res.status });
    let detail = `Live launch failed (${res.status})`;
    try {
      const body = (await res.json()) as { detail?: string | { error?: string; hint?: string } };
      if (typeof body.detail === 'string') detail = body.detail;
      else if (body.detail?.error) detail = body.detail.hint ? `${body.detail.error} — ${body.detail.hint}` : body.detail.error;
    } catch {
      /* keep the status form */
    }
    throw new ApiError(detail, { status: res.status });
  }
  const data = (await res.json()) as { app: string; running: boolean; mode: string };
  logger.info('api.live.launched', { app });
  return data;
}

/**
 * Capture a live-window document as the chat object (POST /api/live/attach).
 * Returns the same OpenedFile shape as openFile (source: "live"), so the
 * caller binds it to chat exactly like an upload.
 */
export async function attachLiveDoc(app: string, index: number | null, session_id?: string): Promise<OpenedFile> {
  logger.info('api.live.attach', { app });
  let res: Response;
  try {
    res = await fetch('/api/live/attach', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: session_id ?? 'default', app, document: index }),
    });
  } catch {
    logger.warn('api.unreachable', { path: '/api/live/attach' });
    throw new ApiError('Controller unreachable at /api/live/attach', { unreachable: true, status: 0 });
  }
  if (!res.ok) {
    logger.warn('api.http-error', { path: '/api/live/attach', status: res.status });
    let detail = `Live attach failed (${res.status})`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* keep the status form */
    }
    throw new ApiError(detail, { status: res.status });
  }
  const data = (await res.json()) as Record<string, unknown>;
  const opened = toOpenedFile(data, session_id ?? 'default');
  logger.info('api.live.attached', { app, doc_id: opened.doc_id });
  return opened;
}

// --- SSE stream reader (fetch + reader; EventSource cannot POST) ---

export interface StreamCallbacks {
  onEvent: (event: StreamEvent) => void;
  onDone: () => void;
  onError: (err: ApiError) => void;
}

/**
 * Parse one SSE `data:` payload line into a StreamEvent.
 * The controller puts the event name on the SSE `event:` line — the data
 * JSON carries no `event` field — so the caller passes it explicitly;
 * a legacy inline `event`/`type` field is still accepted as fallback.
 * Unknown event names return null (ignored, logged at debug).
 */
export function parseStreamPayload(raw: string, eventName?: string): StreamEvent | null {
  let parsed: { event?: string; type?: string } & Record<string, unknown>;
  try {
    parsed = JSON.parse(raw) as { event?: string; type?: string } & Record<string, unknown>;
  } catch {
    return null;
  }
  const name =
    eventName ??
    (typeof parsed.event === 'string' ? parsed.event : (parsed.type as string | undefined));
  switch (name) {
    case 'response.started':
      return {
        type: 'response.started',
        run_id: String(parsed.run_id ?? ''),
        model: String(parsed.model ?? ''),
        team: parsed.team == null ? null : String(parsed.team),
      };
    case 'text.delta':
      return {
        type: 'text.delta',
        delta: String(parsed.delta ?? ''),
        ...(parsed.phase === 'reasoning' || parsed.phase === 'final' ? { phase: parsed.phase } : {}),
      };
    case 'tool.call':
      return {
        type: 'tool.call',
        name: String(parsed.name ?? ''),
        // The controller sends {name, call_id, args}; older shapes vary.
        args: ((parsed.args ?? parsed.arguments) as Record<string, unknown>) ?? {},
      };
    case 'tool.result':
      return {
        type: 'tool.result',
        name: String(parsed.name ?? ''),
        ok: Boolean(parsed.ok),
        // The controller sends {name, ok, error, summary}; accept both.
        summary: String(parsed.summary ?? parsed.error ?? ''),
      };
    case 'response.completed':
      return {
        type: 'response.completed',
        // The controller sends {run_id, records, message_id}; accept all.
        message_id: String(parsed.message_id ?? parsed.run_id ?? ''),
      };
    case 'response.error':
      return { type: 'response.error', message: String(parsed.message ?? '') };
    default:
      logger.debug('stream.unknown-event', { name: String(name ?? '') });
      return null;
  }
}

/**
 * POST the chat request and stream SSE events via fetch reader.
 * Returns an abort function (Esc cancel). Never logs message content.
 */
export function streamChat(body: ChatStreamRequest, cb: StreamCallbacks): () => void {
  const ctrl = new AbortController();
  logger.info('chat.stream.started', { session_id: body.session_id, doc_id: body.doc_id ?? null });

  (async () => {
    let res: Response;
    try {
      res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
    } catch {
      if (ctrl.signal.aborted) return;
      logger.warn('api.unreachable', { path: '/api/chat/stream' });
      cb.onError(new ApiError('Controller unreachable', { unreachable: true, status: 0 }));
      return;
    }
    if (!res.ok || !res.body) {
      cb.onError(new ApiError(`Stream failed (${res.status})`, { status: res.status }));
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split('\n\n');
        buffer = chunks.pop() ?? '';
        for (const chunk of chunks) {
          const lines = chunk.split('\n');
          let eventName: string | undefined;
          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('event:')) {
              eventName = trimmed.slice(6).trim() || undefined;
              continue;
            }
            if (!trimmed.startsWith('data:')) continue;
            const payload = trimmed.slice(5).trim();
            if (payload === '[DONE]') {
              cb.onDone();
              return;
            }
            const event = parseStreamPayload(payload, eventName);
            if (event) cb.onEvent(event);
          }
        }
      }
      cb.onDone();
    } catch {
      if (ctrl.signal.aborted) return;
      cb.onError(new ApiError('Stream interrupted', { status: 0 }));
    } finally {
      reader.releaseLock();
    }
  })();

  return () => {
    ctrl.abort();
    logger.info('chat.stream.cancelled', { session_id: body.session_id });
  };
}

// --- Diagnostics ---

export interface DiagnosticsCheck {
  ok: boolean;
  latency_ms?: number;
  detail?: string;
  configured?: boolean;
  model?: string;
}

export interface DiagnosticsData {
  checks: {
    gateway: DiagnosticsCheck;
    controller: DiagnosticsCheck;
    scaico: DiagnosticsCheck;
    litellm: DiagnosticsCheck;
  };
  // The controller records `at` as an epoch number; older shapes use ISO.
  recent: Array<{ at: string | number; service: string; ok: boolean; detail?: string }>;
}

/**
 * Fetch service health + recent events (GET /api/diagnostics).
 * Why (diagnostics page): the four status cards + recent-events table.
 */
export async function fetchDiagnostics(): Promise<DiagnosticsData> {
  return request('/api/diagnostics');
}

/**
 * Test the Scaico key (POST /api/settings/scaico-key/test {api_key?}).
 * Empty input tests the stored server-side key.
 */
export async function testScaicoKey(api_key?: string): Promise<{ ok: boolean; latency_ms?: number; error?: string }> {
  logger.info('api.scaico.test', {});
  return request('/api/settings/scaico-key/test', {
    method: 'POST',
    body: JSON.stringify(api_key ? { api_key } : {}),
  });
}

// --- Conversations ---

export interface ConversationSummary {
  id: string;
  app?: string;
  title: string;
  // The controller sends updated_at as an epoch number; older shapes use ISO.
  updated_at: string | number;
  message_count: number;
  doc_ids: string[];
}

/**
 * List conversations newest-first (GET /api/conversations).
 * Why (sidebar): grouped resume list with title/time/count/doc badge.
 */
export async function fetchConversations(): Promise<ConversationSummary[]> {
  const data = await request<{ conversations: ConversationSummary[] }>('/api/conversations');
  return data.conversations ?? [];
}

/**
 * Delete a conversation (DELETE /api/conversations/{id}).
 * Clears history, keeps files. 404 = unknown id.
 */
export async function deleteConversation(id: string): Promise<{ deleted: string }> {
  logger.info('api.conversation.delete', { id });
  return request(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

// --- Chat history ---

export interface HistoryMessage {
  role: string;
  text: string;
  at?: number;
}

/**
 * Load persisted thread messages (GET /api/chat/history?session_id=).
 * Why (sidebar resume): repopulates the thread without re-streaming.
 */
export async function loadHistory(session_id: string): Promise<HistoryMessage[]> {
  const data = await request<{ messages: HistoryMessage[] }>(
    `/api/chat/history?session_id=${encodeURIComponent(session_id)}`,
  );
  return data.messages ?? [];
}

// --- Verify actions (POST /api/verify/* if present, else chat-command fallback) ---

export const VERIFY_ACTIONS: VerifyAction[] = [
  { id: 'snapshot', label: 'Snapshot', endpoint: '/api/verify/snapshot' },
  { id: 'restore', label: 'Restore', endpoint: '/api/verify/restore' },
  { id: 'record-view', label: 'Record view', endpoint: '/api/verify/record-view' },
];

/** Probe which verify endpoints exist; missing ones render disabled with tooltip. */
export async function probeVerifyEndpoints(): Promise<Record<string, boolean>> {
  const out: Record<string, boolean> = {};
  await Promise.all(
    VERIFY_ACTIONS.map(async (a) => {
      try {
        const res = await fetch(a.endpoint, { method: 'OPTIONS' });
        out[a.id] = res.ok || res.status === 405; // 405 = exists, wrong method
      } catch {
        out[a.id] = false;
      }
    }),
  );
  return out;
}

export async function runVerifyAction(
  actionId: string,
  payload: { session_id: string; doc_id?: string },
): Promise<{ ok: boolean; summary: string }> {
  const action = VERIFY_ACTIONS.find((a) => a.id === actionId);
  if (!action) throw new ApiError(`Unknown verify action: ${actionId}`);
  logger.info('verify.run', { action: actionId, session_id: payload.session_id });
  return request(action.endpoint, { method: 'POST', body: JSON.stringify(payload) });
}
