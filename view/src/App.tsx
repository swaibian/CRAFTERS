/**
 * App shell: hash routes #/ (chat) + #/settings + #/diagnostics, top bar with
 * connection status dot + active profile label + nav links.
 *
 * Wiring chain: main.tsx → App → (hash route) ChatPage (#/) | Settings
 * (#/settings) | Diagnostics (#/diagnostics). ChatPage: Sidebar (resume/new)
 * → ToolPicker → Dropzone (openFile with session) → opened file binds
 * doc_id+session_id → CrafterChat (model picker) → useChatStream
 * (model/team from response.started) → POST /api/chat/stream.
 */

import { useCallback, useEffect, useState } from 'react';
import { CrafterChat, useChatMessages } from './components/CrafterChat';
import { Diagnostics } from './components/Diagnostics';
import { Dropzone } from './components/Dropzone';
import { LiveApp } from './components/LiveApp';
import { Settings } from './components/Settings';
import { newSessionId, Sidebar } from './components/Sidebar';
import { ToolPicker } from './components/ToolPicker';
import { useChatStream } from './hooks/useChatStream';
import { fetchConversations, fetchProfiles, probeVerifyEndpoints, type OpenedFile } from './lib/api';
import { logger } from './lib/logger';

function useHashRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash || '#/');
  useEffect(() => {
    const onChange = () => setHash(window.location.hash || '#/');
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return hash;
}

function ChatPage({
  connection,
  activeProfile,
  activeProfileLabel,
  activeProfileDefaultModel,
  sessionId,
  onSessionChange,
}: {
  connection: 'online' | 'offline' | 'checking';
  activeProfile: string | null;
  activeProfileLabel: string | null;
  activeProfileDefaultModel: string | null;
  sessionId: string;
  onSessionChange: (id: string) => void;
}) {
  const [app, setApp] = useState<string | null>(null);
  const [opened, setOpened] = useState<OpenedFile | null>(null);
  const [teamId] = useState<string>('');
  const [model, setModel] = useState<string | null>(null);
  const [verifyAvailable, setVerifyAvailable] = useState<Record<string, boolean>>({});
  // Sidebar visibility is persisted between page reloads.
  const [leftOpen, setLeftOpen] = useState(() => {
    try {
      return sessionStorage.getItem('crafter.leftOpen') !== '0';
    } catch {
      return true;
    }
  });
  const [convsOpen, setConvsOpen] = useState(() => {
    try {
      return sessionStorage.getItem('crafter.convsOpen') !== '0';
    } catch {
      return true;
    }
  });
  // The left panel switches between live-app and file-upload workflows.
  const [headlessMode, setHeadlessMode] = useState(() => {
    try {
      const savedMode = sessionStorage.getItem('crafter.leftMode');
      return savedMode ? savedMode === 'headless' : sessionStorage.getItem('crafter.uploadOpen') === '1';
    } catch {
      return false;
    }
  });
  const { messages, appendMessage, patchMessage, pushNotice, setMessages } = useChatMessages();
  const { streaming, model: answeringModel, error, cancel, send } = useChatStream(appendMessage, patchMessage);

  useEffect(() => {
    void probeVerifyEndpoints().then(setVerifyAvailable).catch(() => setVerifyAvailable({}));
  }, []);

  const chatEnabled = opened !== null;
  const liveHint =
    opened?.source === 'live'
      ? `Working on ${opened.live_app ?? 'live app'} · ${
          opened.live_index != null ? `doc ${opened.live_index}` : opened.name
        } (live)`
      : null;

  const handleSend = useCallback(
    (text: string, imageDataUrl?: string) => {
      if (!opened) return;
      send(
        {
          session_id: sessionId,
          doc_id: opened.doc_id,
          message: text,
          profile_id: activeProfile ?? undefined,
          team_id: teamId || undefined,
          model: model ?? undefined,
        },
        text,
        imageDataUrl,
      );
    },
    [opened, send, sessionId, activeProfile, teamId, model],
  );

  const handleVerifyCommand = useCallback(
    (command: string) => {
      // Fallback path when /api/verify/* is absent: send as a chat command.
      pushNotice(`Verify via chat: ${command}`);
      logger.info('verify.fallback-command', {});
    },
    [pushNotice],
  );

  function selectLeftMode(mode: 'open-app' | 'headless') {
    setHeadlessMode(mode === 'headless');
    try {
      sessionStorage.setItem('crafter.leftMode', mode);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="layout">
      {leftOpen ? (
        <aside className="left" aria-label="App link and file input">
          <div className="panel-top">
            <span className="panel-title" id="left-panel-title">
              App
            </span>
            <button
              type="button"
              className="collapse-btn"
              onClick={() => {
                setLeftOpen(false);
                try {
                  sessionStorage.setItem('crafter.leftOpen', '0');
                } catch {
                  /* ignore */
                }
              }}
              aria-label="Collapse app panel"
              aria-controls="left-panel"
              title="Collapse app panel"
            >
              ‹
            </button>
          </div>
          <div id="left-panel" aria-labelledby="left-panel-title">
            <div className="mode-tabs" role="group" aria-label="File opening mode">
              <button
                type="button"
                className={!headlessMode ? 'mode-tab active' : 'mode-tab'}
                aria-pressed={!headlessMode}
                onClick={() => selectLeftMode('open-app')}
              >
                Open app
              </button>
              <button
                type="button"
                className={headlessMode ? 'mode-tab active' : 'mode-tab'}
                aria-pressed={headlessMode}
                onClick={() => selectLeftMode('headless')}
              >
                Headless
              </button>
            </div>
            {headlessMode ? (
              <section className="mode-panel" aria-label="Open a file without a live app">
                <h2 className="plaza-heading-section">Pick an app and file</h2>
                <h3 className="group-sub">1 · Pick app</h3>
                <ToolPicker selected={app} onSelect={setApp} />
                <h3 className="group-sub">2 · Drop file</h3>
                <Dropzone app={app} opened={opened} sessionId={sessionId} onOpened={setOpened} />
              </section>
            ) : (
              <section className="mode-panel" aria-labelledby="link-app-heading">
                <h2 className="plaza-heading-section" id="link-app-heading">
                  Link to open app
                </h2>
                <LiveApp sessionId={sessionId} onOpened={setOpened} />
              </section>
            )}
            {connection === 'offline' && (
              <p className="notice" role="status">
                Controller offline — mock fallback notice: start the controller (:8790) for live
                file-open and chat.
              </p>
            )}
          </div>
        </aside>
      ) : (
        <div className="rail" aria-label="Collapsed app panel">
          <button
            type="button"
            className="collapse-btn"
            onClick={() => {
              setLeftOpen(true);
              try {
                sessionStorage.setItem('crafter.leftOpen', '1');
              } catch {
                /* ignore */
              }
            }}
            aria-label="Expand app panel"
            title="Expand app panel"
          >
            ›
          </button>
          <span className="rail-label" aria-hidden="true">
            App
          </span>
        </div>
      )}
      <Sidebar
        activeSessionId={sessionId}
        open={convsOpen}
        onOpenChange={(open) => {
          setConvsOpen(open);
          try {
            sessionStorage.setItem('crafter.convsOpen', open ? '1' : '0');
          } catch {
            /* ignore */
          }
        }}
        onNewChat={() => {
          const id = newSessionId();
          onSessionChange(id);
          setOpened(null);
          setMessages([]);
          setModel(null);
          logger.info('chat.new', {});
        }}
        onResume={(resumedId, resumedMessages, resumedOpened) => {
          onSessionChange(resumedId);
          setMessages(resumedMessages);
          setOpened(resumedOpened);
          setModel(null);
          logger.info('chat.resumed', {});
        }}
      />
      <main className="center">
        <CrafterChat
          messages={messages}
          streaming={streaming}
          streamError={error}
          chatEnabled={chatEnabled}
          sessionId={sessionId}
          docId={opened?.doc_id ?? null}
          profileId={activeProfile}
          profileLabel={activeProfileLabel}
          activeProfileDefaultModel={activeProfileDefaultModel}
          liveHint={liveHint}
          teamId={teamId || null}
          answeringModel={answeringModel}
          selectedModel={model}
          onModelChange={setModel}
          verifyAvailable={verifyAvailable}
          onSend={handleSend}
          onCancel={cancel}
          onVerifyCommand={handleVerifyCommand}
        />
      </main>
    </div>
  );
}

export function App() {
  const route = useHashRoute();
  const [connection, setConnection] = useState<'online' | 'offline' | 'checking'>('checking');
  const [activeProfile, setActiveProfile] = useState<string | null>(null);
  const [activeProfileLabel, setActiveProfileLabel] = useState<string | null>(null);
  const [activeProfileDefaultModel, setActiveProfileDefaultModel] = useState<string | null>(null);
  // Lifted session id: first conversation (newest) or a fresh uuid.
  const [sessionId, setSessionId] = useState<string>(() => newSessionId());

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchProfiles();
        setConnection('online');
        setActiveProfile(data.active_profile_id);
        const active = data.profiles.find((p) => p.id === data.active_profile_id);
        setActiveProfileLabel(active?.label ?? null);
        setActiveProfileDefaultModel(active?.default_model || null);
        try {
          const convs = await fetchConversations();
          if (convs.length > 0) setSessionId(convs[0]!.id);
        } catch {
          /* conversations endpoint may not exist yet — keep the fresh uuid */
        }
      } catch {
        setConnection('offline');
        try {
          setActiveProfile(sessionStorage.getItem('crafter.activeProfileId'));
        } catch {
          /* ignore */
        }
      }
    })();
  }, [route]);

  return (
    <div className="app">
      <header className="topbar">
        <a href="#/" className="brand" aria-label="ArtCraft Chat home">
          <img src="/assets/swaibian_black.svg" alt="swaibian" />
          <span className="plaza-text-gradient">
            ArtCraft Chat
          </span>
        </a>
        <span
          className={`conn conn-${connection}`}
          role="status"
          aria-label={`Connection: ${connection}`}
          title={connection === 'offline' ? 'Controller unreachable (:8790)' : 'Controller status'}
        >
          ● {connection}
        </span>
        {activeProfile && (
          <span className="muted">
            profile: {activeProfileLabel ?? activeProfile}
          </span>
        )}
        <nav aria-label="Primary">
          <a href="#/">Chat</a>
          <a href="#/settings">Settings</a>
          <a href="#/diagnostics">Diagnostics</a>
        </nav>
      </header>
      {route.startsWith('#/settings') ? (
        <Settings />
      ) : route.startsWith('#/diagnostics') ? (
        <Diagnostics />
      ) : (
        <ChatPage
          connection={connection}
          activeProfile={activeProfile}
          activeProfileLabel={activeProfileLabel}
          activeProfileDefaultModel={activeProfileDefaultModel}
          sessionId={sessionId}
          onSessionChange={setSessionId}
        />
      )}
    </div>
  );
}
