# 04 — Security & Sandboxing

Read this before you point an agent at these apps. Several of them will run with your full user
permissions by default, and an agent driving a GUI-simulation tool is a much larger blast radius
than an agent calling a REST API.

---

## 1. What the apps already do for you

This is genuinely well-designed upstream work. PhotoCraft in particular has a threat model in
its mdBook (`book/src/security/`, `book/src/automation/security-model.md`).

### 1.1 Filesystem capability roots

Where present, roots are granted **independently** at launch:

| App | Flags |
|---|---|
| photocraft | `--automation-read-root`, `--automation-write-root` |
| vectorcraft | `--automation-read-root`, `--automation-write-root` |
| effectcraft | `--automation-read-root`, `--automation-write-root` |
| pdfcraft | `--root DIR` (single root, covers reads **and** writes **and** commands run via common tools) |

Semantics (PhotoCraft's model, which the others follow):
- Paths must be relative to the root, or absolute-but-beneath-it.
- Absent root → **no filesystem authority at all** (fails closed).
- Absolute paths are compared to the root as *text*; the remainder is checked like a relative
  path. Nothing is resolved on the filesystem during the check.
- **Rejected before any file effect:** absolute paths outside the root, `..` traversal,
  alternate separators in a relative path, Windows drive/device/stream prefixes, malformed
  components, symlink escapes.
- Read and write authority are independent.
- The parent of a new output file must already exist.

Environment-variable equivalents exist for the desktop app only
(`PHOTOCRAFT_AUTOMATION_READ_ROOT` / `_WRITE_ROOT`, and the token vars) — **not** for the headless
CLI MCP server. For CLI modes, pass the flags explicitly.

### 1.2 Ambient-path commands are disabled under automation

> `automation command '<id>' uses ambient filesystem paths and is disabled; use
> capability-scoped document methods`

Applies to `file.open`, `file.save`, `file.saveAs`, `file.saveACopy` (use `app.open`/`app.save`),
and to path parameters on other commands (`layer.exportAs {path}`,
`filter.distort.displace {mapPath}`, preset imports, plug-in install/reload). Preference updates
that could indirectly grant filesystem access are refused (`colorSettings`, `scriptEvents`,
`historyLog`, `plugIns`, `scratchDisks`). `image.mode.*` is refused because it loads profiles from
preferences.

Source: `crates/automation/src/workspace.rs`. The same rules apply to recorded actions and
synthetic UI input — interactive desktop commands keep their normal access.

### 1.3 Control channel

- **Loopback only.** The listener binds `127.0.0.1` and does not accept remote addresses.
- **Bearer token**, 256-bit, delivered via `--control-token-file` (never the command line).
  `0600` on Unix; user-only ACL on Windows. Env: `<APP>_CONTROL_TOKEN` / `_TOKEN_FILE`.
  With neither configured, a token is generated per launch and written to **stderr**.
- **First request on every connection must be `auth`.** Nothing else dispatches before it.
- 1 MiB max request line, 8 MiB max reply, 16 concurrent connections, 30 s socket timeout,
  256 steps max per batch.
- Unencrypted. Upstream says so explicitly: *"do not tunnel or proxy it to an untrusted host."*
- WordCraft differs: a **control key** from `WORDCRAFT_CONTROL_KEY` or the app-written key file,
  sent only to loopback.
- PdfCraft differs: a **control file** (JSON, owner/mode validated, <100 KiB) rather than a port.

Upstream's own framing of the residual risk:

> *"TCP control uses a bearer token, not client identity or general per-method authorization. A
> client that possesses the token receives the non-filesystem control surface, including UI input,
> command execution, and application control."*

### 1.4 No unsafe, no panics

Every Craft workspace forbids `unsafe` and denies `clippy::unwrap_used`, `expect_used`, `panic`,
`unimplemented`, `todo`, `unreachable`. MCP servers additionally wrap each request in
`catch_panic`, so a panic becomes a tool error and the server keeps serving.

That is good engineering. It is **not** a sandbox: a `deny(clippy::panic)` is a lint, and
memory/CPU are not bounded.

---

## 2. What the apps do **not** do for you

### 2.1 Confinement coverage is incomplete — this is the main risk

Measured from each repo's `docs/mcp.md`:

| App | Root confinement | Status |
|---|---|---|
| photocraft | `--automation-read-root` / `--automation-write-root` | Full |
| vectorcraft | `--automation-read-root` / `--automation-write-root` | Full |
| effectcraft | `--automation-read-root` / `--automation-write-root` | Full |
| pdfcraft | `--root` | Full (read + write together) |
| **filmcraft** | **none** | *"there are no folder-confinement flags such as `--automation-read-root`, so the server can read and write wherever the user can."* |
| **lightcraft** | **none found** | — |
| **designcraft** | **none found** | — |
| **gridcraft** | **none found** | — |
| **cadcraft** | **none found** | — |
| **deckcraft** | **none found** | — |
| **soundcraft** | **none found** | — |
| **wordcraft** | **none found** | — |

**Eight of twelve apps have no filesystem confinement at all.** In headless MCP mode they inherit
the full permissions of whoever launched them. Confirmed absent ≠ confirmed safe.

### 2.2 No per-method authorization

There is a bearer token, not method-level scopes. Possession of the token = the whole non-
filesystem control surface, including synthetic UI input and `app.quit`.

### 2.3 No resource limits

No memory cap, no CPU cap, no disk quota, no per-request cost accounting. A `render_preview` at
`max_side: 4096` on a 20,000-pixel-wide document will try. A `render_video` will run until it
finishes unless cancelled.

### 2.4 No encryption

Control channels are plaintext JSON on loopback. Fine on loopback; not fine through a container
network, a VM bridge, an SSH-forwarded port, or a shared host with visible process tables.

### 2.5 The apps are not hardened against a *hostile* agent

The design assumes the agent is a well-behaved operator. There is no undo across sessions, no
transactional batch (except PhotoCraft's `command_batch {atomic: true}`), and no dry-run mode.
An agent that misunderstands a command can destroy a document irrecoverably.

---

## 3. Required controls in your gateway

### 3.1 Default-deny policy

```rust
struct AppPolicy {
    binary:        PathBuf,
    mode:          Mode,                  // Headless | Bridge(SocketAddr)
    read_root:     Option<PathBuf>,       // None + sandboxed=true => refuse ALL file tools
    write_root:    Option<PathBuf>,
    sandboxed:     bool,                  // required when the app has no confinement flags
    allow_read:    bool,
    allow_write:   bool,
    max_concurrency: usize,               // per app
    call_timeout:  Duration,              // default 60s
    idle_timeout:  Duration,              // default 10 min
    max_child_mem: Option<u64>,           // your guard, not the app's
}
```

- **Default `sandboxed: true`.** For the eight unconfined apps, enforce the roots *yourself*, in
  the gateway, by inspecting and rewriting `path` parameters before forwarding. This is
  imperfect — an app could reach the filesystem by a route you did not anticipate — so also:
- **Run unconfined apps in a container or VM with a bind-mounted scratch dir** if the agent is
  not fully trusted. macOS: a sandbox-exec profile or a dedicated user account. Linux: bubblewrap
  or a user namespace. Windows: an AppContainer or a low-privilege account.
- **`allow_write: false` by default.** Flip it on per session, not globally.

### 3.2 Path interception

```rust
fn confine(p: &str, root: Option<&Path>, write: bool) -> Result<PathBuf, PolicyError> {
    let root = root.ok_or(PolicyError::NoAuthority)?;
    // reject: absolute outside root, "..", "\\" in a relative path, drive/device prefixes,
    //          empty components, NUL, symlink escapes after canonicalisation
}
```

Mirror upstream's rules exactly — they are correct. Also canonicalise and re-check after
resolution to catch symlink escapes, and check the **parent exists** for writes.

Be honest about coverage: some commands take paths nested inside `params` (`layer.exportAs
{path}`, `filter.distort.displace {mapPath}`), and PhotoCraft's bridge refuses those anyway — but
on the apps that do *not* refuse them, you need a recursive scan of `params` for any string that
looks like a path and looks absolute or contains `..`. Over-block on ambiguity.

### 3.3 Credential handling

| Credential | Rule |
|---|---|
| Control token | `--control-token-file` only. Never on a command line (visible in `ps`). Never in the MCP args array, never in logs. `0600`. |
| Cloud API key | Gateway config / env only. Never passed through an agent tool call. Never logged — note the *server* logs the key at `warn!` on lookup failure; don't copy that. |
| WordCraft control key | `WORDCRAFT_CONTROL_KEY` env on the CLI process, not a flag. |

Redact in logs: any `Authorization` header, any `*_CONTROL_TOKEN*`, any path outside the roots.

### 3.4 Transport safety

- Bind nothing. The gateway is stdio.
- For bridge mode, **verify the peer is loopback** before connecting; refuse `0.0.0.0`, LAN
  addresses, and anything that resolves off-host.
- Do not forward a control channel over SSH, a container port mapping, or a reverse proxy.
- If you must cross a host boundary, use an SSH **local** forward (`ssh -L`) so the socket stays
  on loopback on both ends. Never `ssh -R`.

### 3.5 Resource governance

- Per-call timeout, default 60 s. Long commands: pass `wait: false`, return `{job, pending}`,
  let the agent poll `jobs.list`. Cap job count per session.
- Cap image dimensions on `render_preview`/`render_slide`/etc. yourself — upstream caps `max_side`
  at 1024–4096, which is not enough on a 20k-pixel document.
- Disk quota per session `write_root`. Prune on exit.
- Max concurrency per app (1 for stateful GUI apps; document operations are order-sensitive).
- On bridge transport failure: **never auto-retry a write.** Retry pure reads only
  (`ui_inspect`, `doc_inspect`, `command_list`, `jobs_list`, `session_list`, `ui_screenshot`).

### 3.6 Provenance and reversibility

- Set an author/identity where supported: `wordcraft-cli mcp --author "…"` / `file.setAuthor`;
  tracked changes and comments then attribute the agent. Consider an equivalent for other apps.
- **Snapshot before destructive work.** Before any batch over an existing document, copy the
  file into the session's asset store with a timestamp. Cheap insurance.
- Log every tool call (app, tool, params hash, result status, duration) to a per-session JSONL
  audit log. You will need it when an agent does something surprising.

---

## 4. Threat summary

| Threat | Mitigation | Residual |
|---|---|---|
| Agent reads files outside intent | Roots + recursive `params` path scan + container | Apps without confinement have no in-process enforcement |
| Agent overwrites user data | `write_root` + snapshot + `allow_write` default off | `command_batch` is not transactional except PhotoCraft `atomic` |
| Control token exfiltration via `ps` | `--control-token-file`, `0600` | Environment of the process is still readable by the same user |
| Bridge replay / stale connection | One authenticated connection, 55 s client timeout below the 60 s server deadline, proactive reconnect when idle | Writes may have landed before a failure; no idempotency keys |
| Cloud credit burn | Per-session credit budget, `cost` estimate before `generate` | No server-side per-key cap observed |
| Runaway render | Per-call timeout, cancellation forwarding, dimension caps | No app-side resource governor |
| Cross-app data leak | Separate asset namespaces per session; provenance log | None observed |
| Malicious document parsing | Apps are fuzzed (`docs/fuzzing.md`, security book chapter) and deny `unsafe` | Not independently audited here |

---

## 5. Operator checklist before going live

1. Decide the trust level of the agent. Trusted operator → headless + roots is fine.
   Untrusted/semi-trusted → container per app, `allow_write` off, no cloud key.
2. Grant roots explicitly per session. Never a home directory. Never `/`.
3. Keep cloud credentials out of the agent's reach entirely.
4. Enable the audit log.
5. Test the unconfined apps (filmcraft, lightcraft, designcraft, gridcraft, cadcraft, deckcraft,
   soundcraft, wordcraft) inside a container before any real work.
6. Read `photocraft/book/src/automation/security-model.md` and
   `photocraft/book/src/security/automation-security.md` — they are the org's own statement of
   this problem and are better than anything written here.