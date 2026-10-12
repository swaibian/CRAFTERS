# Sources

Everything consulted to produce these documents. Research conducted 2026-10-11.

---

## Organisation

<https://github.com/storytold>

Repo list retrieved with:
`gh api /orgs/storytold/repos --paginate -q '.[] | [.name, .language, .stargazers_count, .description] | @tsv'`

---

## Repositories cloned and analysed

Shallow clones (`--depth 1`, `--filter=blob:none` for the apps) to a temporary working directory:

| Repo | Size | Purpose in this research |
|---|---|---|
| `storytold/photocraft` | 56 M | Reference implementation (family A, `rmcp`) |
| `storytold/filmcraft` | 56 M | Family A, richest agent docs |
| `storytold/effectcraft` | 39 M | Family A, ExtendScript engine |
| `storytold/vectorcraft` | 52 M | Family B, most complete MCP crate |
| `storytold/lightcraft` | 45 M | Family B |
| `storytold/pdfcraft` | 46 M | Family A, task-oriented tools + `--root` |
| `storytold/designcraft` | 23 M | Family B, script format |
| `storytold/wordcraft` | 25 M | Family B, author attribution |
| `storytold/gridcraft` | 12 M | Family B, compact |
| `storytold/cadcraft` | 14 M | Family B, `command_line` tool |
| `storytold/deckcraft` | 11 M | Family B, `call_app` |
| `storytold/soundcraft` | 14 M | Family A, smallest MCP |
| `storytold/craft-libs` | 768 K | Shared crates + engineering rules |
| `storytold/craft-launcher` | 6.0 M | Programmatic-interface audit |
| `storytold/craft-common-actions` | 240 K | Confirmed CI/CD only, not agent-related |
| `storytold/artcraft-services` | 1.6 G | Cloud REST API inventory |
| `storytold/craft-repo-status-app` | 1.4 M | Skipped (CI dashboard, not relevant) |

Also reviewed and found redundant: local copies of `photocraft-main`, `vectorcraft-main`,
`lightcraft-main`, `pdfcraft-main`, `gridcraft-main`, `wordcraft-main` in
`~/Downloads/CRAFT` — these are zip extractions of the same `main` branches already cloned, and
contained nothing additional.

---

## Primary in-repo sources read

### MCP servers

| Path | Note |
|---|---|
| `vectorcraft/crates/mcp/src/lib.rs` | Best architecture doc-comment in the org; the family-B pattern |
| `vectorcraft/crates/mcp/src/server.rs` | Protocol versions, `handle_line`, notification queueing, `catch_panic`, 2026-07-28 cache fields |
| `vectorcraft/crates/mcp/src/tools.rs` (992 L) | Tool schema conventions, `annotations`, `writes_file` override |
| `vectorcraft/crates/mcp/src/{backend,headless,resources,prompts,logging}.rs` | `Backend` trait, `Remote`, resource templates, `PROMPTS` |
| `lightcraft/crates/mcp/src/*.rs` | Adds `progress.rs`, `base64.rs` |
| `designcraft`, `gridcraft`, `cadcraft`, `deckcraft`, `wordcraft` `crates/mcp/src/{server,tools}.rs` | Per-app tool tables |
| `photocraft/crates/automation/src/server.rs` (987 L) | `rmcp` `#[tool_router]`, `BridgeClient` |
| `photocraft/crates/automation/src/server/conventions.rs` | `annotated()` — central tool-annotation policy |
| `photocraft/crates/automation/src/{rpc,bridge,headless,workspace,security,files,budgets}.rs` | `serve` protocol, bridge client, filesystem policy |
| `filmcraft/crates/automation/src/{server,bridge,long_job}.rs` | `rmcp`, progress, cancellation |
| `effectcraft/crates/automation/src/{server,tools,bridge,confine}.rs` | Largest hand-written tool table (1008 L) |
| `effectcraft/crates/script/src/*` | ExtendScript / AE expression runtime |
| `pdfcraft/crates/automation/src/{mcp,tools}.rs` | `tools()` builder, `tool_for_command()`, `--compact` |
| `pdfcraft/apps/pdfcraft-cli/src/main.rs` (`USAGE`) | Control-file transport, `--script` |
| `soundcraft/crates/automation/src/mcp.rs` (251 L) | Minimal complete MCP server |

### Documentation

| Path | Note |
|---|---|
| `photocraft/docs/mcp.md`, `docs/control-protocol.md` | Most complete pair in the org |
| `photocraft/book/src/architecture/automation.md` | The cross-transport diagram |
| `photocraft/book/src/automation/security-model.md` | Automation security model |
| `photocraft/book/src/security/automation-security.md` | Automation security posture |
| `photocraft/book/src/security/{threat-model,trust-boundaries}.md` | Referenced, not exhaustively read |
| `photocraft/book/src/architecture/command-engine.md` | Registry design |
| `photocraft/docs/{architecture,plugins,parity-checklist}.md` | Structure, extension points |
| `filmcraft/docs/agents.md` | Two-part narrative: using FilmCraft from an agent, developing it as one |
| `effectcraft/docs/agents.md` + `docs/scripting-parity.md` | Best "three ways in" table; AE scripting coverage |
| `effectcraft/docs/{effects,plugins,footage,preferences}.md` | Domain surface |
| `designcraft/docs/agents.md` | Script format and `$N.path` semantics |
| `vectorcraft/docs/mcp.md` (3,154 L) | Largest protocol reference |
| `lightcraft/docs/mcp.md` (304 L) + `docs/{ai-masks,background-tasks,apple-photos}.md` | |
| `pdfcraft/docs/mcp.md`, `docs/development.md` | `--root`, control file |
| `gridcraft/docs/{mcp,cli,formula-input,function-parity}.md` | |
| `cadcraft/docs/mcp.md`, `docs/{geometry-parity,plot-styles,plotters}.md` | |
| `deckcraft/docs/mcp.md`, `docs/{animation-parity,slideshow-parity}.md` | `call_app` |
| `soundcraft/docs/mcp.md`, `docs/plugin-parity.md` | |
| `wordcraft/docs/mcp.md`, `docs/{typing-parity,layout-parity,zotero}.md` | Author attribution |
| `craft-libs/AGENTS.md`, `craft-launcher/AGENTS.md`, `craft-launcher/CLAUDE.md` | Engineering rules |
| `artcraft-services/AGENTS.md`, `crates/service/web/storyteller_web/AGENTS.md` | Monorepo layout, API-compatibility rule |
| `artcraft-services/_docs/omni_api/artcraft_omni_api.md` (625 L) | The official programmatic API guide |

### Launcher

| Path | Note |
|---|---|
| `craft-launcher/apps/artcraft-launcher/src/main.rs` | Entire arg surface: `--version`, `--hidden` |
| `craft-launcher/crates/core/src/catalog.rs` | `SUITE: [CraftApp; 12]`, bundle ids, repo mapping |
| `craft-launcher/crates/core/src/{feed,platform,release,protocol}.rs` | Feed schema, asset naming, internal `Command`/`Event` |
| `craft-launcher/crates/native/src/{single_instance,install,detect,paths,backend,source,feed_throttle,self_update}.rs` | The 47413 socket; `launch_binary(path, &[])`; paths; update flow |

### Cloud services

| Path | Note |
|---|---|
| `artcraft-services/crates/service/web/storyteller_web/src/http_server/routes/` | Route registrars (legacy / application / service) |
| `…/routes/application_routes/{omni_api_routes,omni_gen_routes,generate_routes,media_files_routes,job_routes,user_routes,api_keys_routes,mcp_session_routes}.rs` | Full route inventory |
| `…/routes/application_routes/{credits,subscription,wallet,stripe_artcraft,folder,tag,prompt,character,comment,moderation}_routes.rs` | Domain routes |
| `…/http_server/user_lookup/**` | `require_api_key_user`, `require_any_session_or_key`, etc. |
| `…/src/docs/api_doc.rs` (1,641 L) | `#[derive(OpenApi)]`, ~350 paths, ~700 schemas |
| `…/src/{api_doc_cli,api_doc_server}.rs` | Spec generation + SwaggerUI on :8989 |
| `…/endpoints/omni_api/generate/{video,image}/` | Request types and validation order |
| `…/endpoints/omni_api/upload/{image,video,audio}/` | Multipart forms and MIME allow-lists |
| `…/endpoints/omni_api/job_status/job/get_job_status_handler.rs` | State machine, `"None"` filtering, keepalive |
| `crates/api_clients/artcraft/artcraft_api_defs/` | ~105 route path constants |
| `crates/api_clients/artcraft/artcraft_client/src/{utils/api_host,credentials,endpoints}/` | Host list; cookie-only credential set |
| `crates/api_clients/artcraft/artcraft_api_keys/src/lib.rs` | `artcraft_api_` format, redaction discipline |
| `crates/cli/production/support-tool/` | The only CLI touching the HTTP API |
| `_tools/postman/` | openapi-directory-format collection (partly stale) |
| `artcraft-services/README.md`, `.env`, `build/Tiltfile` | Hosts, ports, dev config |
| `artcraft-services/secrets/` | Contains only `.gitkeep` |

---

## External references

| Resource | URL |
|---|---|
| Model Context Protocol | <https://modelcontextprotocol.io> |
| MCP spec revisions implemented | `2026-07-28`, `2025-06-18`, `2025-03-26`, `2024-11-05` |
| `rmcp` Rust SDK | `rmcp` crate (used by photocraft, filmcraft) |
| Production API | `https://api.storyteller.ai` |
| Legacy API alias | `https://api.fakeyou.com` |
| Browser webapp | `https://app.getartcraft.com` |
| Marketing site | `https://getartcraft.com` |
| Published API reference | `https://storyteller-docs.netlify.app/` |
| Launcher feed endpoint | `https://api.storyteller.ai/v1/craft_apps/release_info` |
| Support Discord (from `pdfcraft-cli --help`) | <https://discord.gg/artcraft> |

---

## Claims that could NOT be verified

Recorded explicitly so they are not mistaken for findings.

1. **Whether the CLI binaries in current releases behave exactly as the `main` branches read
   here.** Version drift between a tagged release and `main` was not checked per app.
2. **Whether `--compact` exists in released pdfcraft/lightcraft builds.** PdfCraft gates `mcp`
   behind a cargo feature (`default = ["mcp"]`); a build without it errors with *"this build
   leaves out the MCP server"*. Check with `<app>-cli mcp --help`.
3. **Whether `deckcraft`'s `call_app` can target other Craft apps.** The tool exists; its target
   set was not traced. **This is the highest-value next investigation.**
4. **Whether confinement flags are present in released binaries** for the 8 apps whose docs do
   not mention them. Absence from `docs/mcp.md` is strong but not conclusive.
5. **No functional test was run.** Nothing was built or executed; this analysis is entirely
   static, from sources and docs.
6. **`crates/core/tests/fixtures/`** is referenced by `craft-launcher/AGENTS.md` but absent from
   the shallow clone (test data, not relevant here).
7. **Path constant drift** found in `artcraft_api_defs` (`user_signup/subscription_checkout` vs
   `user_signup_subscription_checkout`) was not tested against a live server.

---

## Suggested next research step

Clone `storytold/deckcraft` at full depth and trace `call_app` end to end. If one Craft app can
already invoke another over a documented protocol, the cross-app gateway is partly built and your
work becomes an extension rather than a from-scratch build.