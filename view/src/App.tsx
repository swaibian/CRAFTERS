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
  sessionId,
  onSessionChange,
}: {
  connection: 'online' | 'offline' | 'checking';
  activeProfile: string | null;
  activeProfileLabel: string | null;
  sessionId: string;
  onSessionChange: (id: string) => void;
}) {
  const [app, setApp] = useState<string | null>(null);
  const [opened, setOpened] = useState<OpenedFile | null>(null);
  const [teamId] = useState<string>('');
  const [model, setModel] = useState<string | null>(null);
  const [verifyAvailable, setVerifyAvailable] = useState<Record<string, boolean>>({});
  const { messages, appendMessage, patchMessage, pushNotice, setMessages } = useChatMessages();
  const { streaming, model: answeringModel, error, cancel, send } = useChatStream(appendMessage, patchMessage);

  useEffect(() => {
    void probeVerifyEndpoints().then(setVerifyAvailable).catch(() => setVerifyAvailable({}));
  }, []);

  const chatEnabled = opened !== null;

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

  return (
    <div className="layout">
      <aside className="left" aria-label="Tool picker and file input">
        <h2 className="plaza-heading-section">1 · Pick app</h2>
        <ToolPicker selected={app} onSelect={setApp} />
        <h2 className="plaza-heading-section">2 · Drop file</h2>
        <Dropzone app={app} opened={opened} sessionId={sessionId} onOpened={setOpened} />
        <h2 className="plaza-heading-section">3 · Live app window</h2>
        <LiveApp sessionId={sessionId} onOpened={setOpened} />
        {connection === 'offline' && (
          <p className="notice" role="status">
            Controller offline — mock fallback notice: start the controller (:8790) for live
            file-open and chat.
          </p>
        )}
      </aside>
      <Sidebar
        activeSessionId={sessionId}
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
        <a href="#/" className="brand" aria-label="Crafter Chat home">
          <img src="/assets/swaibian_black.svg" alt="Swaibian" />
          <span className="plaza-text-gradient">
            Crafter Chat
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
          sessionId={sessionId}
          onSessionChange={setSessionId}
        />
      )}
    </div>
  );
}
