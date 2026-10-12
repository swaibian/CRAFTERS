# Crafter Chat View

Vite + React + TypeScript chat UI for the Crafter gateway (EPIC_002, TC-A + TC-B).

## Prerequisites

- Node 20+, npm reachable
- Controller (FastAPI) at `http://127.0.0.1:8790` for live data (optional — the view degrades gracefully with a mock-fallback notice when it is down)

## Install

```sh
npm i
```

## Run (dev)

```sh
npm run dev
```

Vite serves on **http://127.0.0.1:5173** and proxies `/api/*` → `http://127.0.0.1:8790` (see `vite.config.ts`). Open `#/` for chat, `#/settings` for the setup view.

## Build

```sh
npm run build   # tsc -b + vite build → dist/
```

## Test

```sh
npm test        # vitest run
npm run lint    # oxlint
```

## Layout

- `src/lib/api.ts` — typed controller client (teams, profiles CRUD, file open, SSE stream reader, verify actions)
- `src/lib/logger.ts` — redacting logger (keys/prompts/content/image data never logged)
- `src/lib/chat.ts` — shared message/toolcall model
- `src/lib/image.ts` — client-side picture resize (max 1024px)
- `src/hooks/useChatStream.ts` — SSE subscription + chunk assembly
- `src/components/ToolPicker.tsx` — app cards (photocraft/gridcraft/pdfcraft live, rest "soon")
- `src/components/Dropzone.tsx` — drag/drop file open + opened-file header
- `src/components/CrafterChat.tsx` — thread, composer, working pill
- `src/components/ToolcallView.tsx` — inline toolcall + collapsible detail + verify actions
- `src/components/Settings.tsx` — AI Endpoints + Keys setup view
- `src/App.tsx` — hash router + top bar (connection dot, active profile)

## Keys & privacy

API keys render masked only (`api_key_masked`), are sent only in POST/PUT bodies to the controller, and never appear in logs, localStorage, or the DOM. Only the active profile *id* is kept in `sessionStorage`.
