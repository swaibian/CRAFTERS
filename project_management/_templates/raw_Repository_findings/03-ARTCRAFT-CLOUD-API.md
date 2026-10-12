# 03 — The ArtCraft Cloud REST API (a second, separate surface)

**Source:** `storytold/artcraft-services` — the Rust/Actix-web backend, MySQL + Redis +
Elasticsearch, plus TypeScript frontends. **Not** a Craft app; this is the hosted service behind
getartcraft.com.

This matters to your project because it is **the one part of the ecosystem with a documented,
public, API-key-authenticated REST interface**, and its generation capabilities are *not*
available in the desktop apps (which are offline-first and local).

---

## 1. Two hostnames, two generations

| Host | Role |
|---|---|
| `https://api.storyteller.ai` | **Current** API. `_docs/omni_api/artcraft_omni_api.md:33` warns explicitly: *"Our APIs are hosted on `api.storyteller.ai`, not `api.getartcraft.com`. This is not a typo."* |
| `https://api.fakeyou.com` | Legacy alias, still in `ApiHost::FakeYou` and the stale Postman production env |
| `http://localhost:12345` | Dev (bind `0.0.0.0:12345`, env `BIND_ADDRESS`) |
| `https://app.getartcraft.com` | Browser webapp |
| `https://cdn-2.fakeyou.com` | Media CDN |

---

## 2. Three generation surfaces — pick the right one

| Surface | Base path | Auth | Covers |
|---|---|---|---|
| **Omni API** | `/v1/omni_api/*` | **API key only** (no cookies) | image + video generate, 3 uploads, job status. **This is the documented programmatic API.** |
| **Omni Gen** | `/v1/omni_gen/*` | cookie **or** API key **or** MCP session | image, video, **audio, mesh, splat** + `/cost/*` + `/models/*` |
| **Legacy per-model** | `/v1/generate/*` | **cookie session only** — rejects API keys | ~48 model-specific endpoints |

> Note the asymmetry: audio/3D/mesh are only under `/v1/omni_gen/generate/*`, but that surface
> *also* accepts API keys (via `require_any_session_or_key`). So an API-key client can reach
> everything — just not under the `omni_api` prefix.

---

## 3. Authentication

### API key

Get one at `https://app.getartcraft.com/` → Account → Settings → API Keys (gated; contact the
team to enable). Format: prefix `artcraft_api_` + 40 Crockford base32 chars = **53 chars**, shown
once. Stored in MySQL, looked up fresh on every request (never cached), soft-deleted on revoke.

Three header forms accepted (scheme case-insensitive):

```http
Authorization: Bearer artcraft_api_xxxxxxxx
Authorization: Key    artcraft_api_xxxxxxxx
Authorization: artcraft_api_xxxxxxxx
```

> **Critical behaviour:** if an `Authorization` header is present **at all**, cookies are *never*
> consulted. A bad header credential is a 401, never a fallback to cookies.

### MCP session credential

`mcp_session_`-prefixed, created via `POST /v1/mcp/session/create` (cookie or API key).
`private_session_token` + `private_refresh_token` are returned **exactly once** and rotated on
refresh. Valid alternative credential on the Omni Gen surface — this is the server-side MCP
integration point.

### Public endpoints (no auth)

`/_status`, `/server_info`, `/detect_locale`, `/v1/status_alert_check`,
`POST /v1/omni_gen/cost/*`, `GET /v1/omni_gen/models/*`, `POST /v1/generate/cost_estimate/*`,
`GET /v1/media_files/file/{token}`, `GET /v1/jobs/job/{token}`, plus the login/SSO/password-reset
and Stripe/FAL webhook routes.

> **`GET /v1/jobs/job/{token}` is fully public** — the job token *is* the capability. The source
> comment: *"NB: Since this is publicly exposed, we don't query sensitive data."* The
> `/v1/omni_api/` twin of the same job **does** require the API key.

Cost and model-discovery endpoints being public means an agent can enumerate models and prices
before it has a key. Useful.

---

## 4. The Omni API in detail

Base: `https://api.storyteller.ai`

### 4.1 Generate video — `POST /v1/omni_api/generate/video` → async

`OmniApiVideoGenerateRequest`:

| Field | Type | Notes |
|---|---|---|
| `idempotency_token` | String | **Required**, UUID format, duplicates rejected |
| `model` | `CommonVideoModel` | **Required** |
| `prompt`, `negative_prompt` | String | |
| `start_frame_image_media_token` \| `start_frame_image_url` | | Mutually exclusive |
| `end_frame_image_media_token` \| `end_frame_image_url` | | Mutually exclusive |
| `reference_image_media_tokens` \| `reference_image_urls` | Vec | Mutually exclusive |
| `reference_video_media_tokens` \| `reference_video_urls` | Vec | Mutually exclusive |
| `reference_audio_media_tokens` \| `reference_audio_urls` | Vec | Mutually exclusive |
| `reference_character_tokens` | Vec | `@CharacterName` in the prompt |
| `resolution`, `aspect_ratio`, `bitrate`, `quality` | enums | e.g. `wide_sixteen_by_nine` |
| `output_format` | enum | `mp4`/`mov` (Seedance 2.5 only) |
| `duration_seconds`, `video_batch_count` | u16 | |
| `generate_audio` | bool | |

Response: `{ success, inference_job_token, all_job_tokens }`

URL inputs: must be `http(s)`, redirects followed (≤10), type sniffed from bytes (video refs must
be `mp4`; images `jpeg/png/gif/webp`).

### 4.2 Generate image — `POST /v1/omni_api/generate/image` → async

`idempotency_token`, `model`, `prompt`, `image_media_tokens` | `image_urls` (exclusive),
`resolution`, `aspect_ratio`, `quality`, `image_batch_count`, `adjust_horizontal_angle`,
`adjust_vertical_angle`, `adjust_zoom`.
Response: `{ success, inference_job_token }`.

### 4.3 Poll

```http
GET /v1/omni_api/job_status/job/{token}              → { success, state }
GET /v1/omni_api/job_status/batch?tokens=a&tokens=b   → { success, job_states: [...] }
```

States: non-terminal `pending`, `started`, `attempt_failed`; terminal `complete_success`,
`complete_failure`, `dead`, `cancelled_by_user`, `cancelled_by_system`.

Result URL: `state.maybe_result.media_links.cdn_url`, plus thumbnail templates
(`maybe_video_previews.{still,animated,…}`, `maybe_thumbnail_template` with a `{WIDTH}` slot).

```python
# minimal poll loop
import time, requests
H = {"Authorization": f"Bearer {KEY}"}
r = requests.post("https://api.storyteller.ai/v1/omni_api/generate/image",
                  headers=H, json={"idempotency_token": str(uuid.uuid4()),
                                   "model": "Seedream4", "prompt": "a red fox in snow"})
tok = r.json()["inference_job_token"]
while True:
    s = requests.get(f"https://api.storyteller.ai/v1/omni_api/job_status/job/{tok}",
                     headers=H).json()["state"]
    if s in {"complete_success","complete_failure","dead","cancelled_by_user","cancelled_by_system"}:
        break
    time.sleep(3)
url = s.get("maybe_result", {}).get("media_links", {}).get("cdn_url")
```

### 4.4 Uploads

`POST /v1/omni_api/upload/{image,video,audio}` — multipart.
`uuid_idempotency_token` (required), `file` (≤512 MiB), `maybe_title`, `maybe_visibility`,
`maybe_generation_provider`. Returns `{ success, media_file_token }`.
MIME allow-lists: image `jpeg/png/gif/webp`; audio `aac/m4a/mpeg/ogg/opus/x-flac/x-wav/mp4`;
video `mp4/quicktime` (MOV preserved without transcoding).

---

## 5. Models available (the cloud-only capability)

| Kind | Examples |
|---|---|
| **Image** | Flux1Dev, Flux1Schnell, FluxPro11(+Ultra), GptImage1/1p5/**2**, GptImage2p5Flare, GptImage2p5Sunburst, GrokImagineImage(+Quality), **Midjourney7/7Niji/8**, NanoBanana/2/Pro, Seedream4/4p5/5Lite/5p0Pro(+Pro/Ultra), Flux2LoraAngles, QwenEdit2511Angles |
| **Video** | GrokVideo, GrokImagineVideo(1/1p5), Flux3(+Draft), Kling 1.6/2.1/2.5/2.6/3.0, HappyHorse1p0, Wan3p0(+Prime), Minimax H3/Turbo/Ultra, Seedance 1.0Lite/1.5Pro/2.0(+Fast/BytePlus/Ultra/Mini)/2.5(+Preview/Ultra), **Sora2 / Sora2Pro**, Veo2/Veo3/Veo3Fast/Veo3p1(+Fast/Lite), ViduQ3(+Turbo) |
| **Audio / music** | SunoMusic, SunoRemix, SunoSounds, SunoSample, SeedAudio1p0 |
| **3D mesh** | Hunyuan3d2p0/2p1/3/3Sketch/3p1Pro/3p1Rapid/3p1Part/3p1SmartTopology, Tripo3dH3p1, MeshyV6, Rodin2p5Fast |
| **Gaussian splat** | Marble0p1Mini/0p1Plus/1p0/1p0Draft/1p1/1p1Plus, TripoSplat |

**Not available:** lipsync and voice cloning. Lipsync exists only as the deprecated
`POST /v1/workflows/enqueue_lipsync`; TTS is legacy `/v1/tts/inference` or
`/v1/omni_gen/generate/audio`.

**Cost before generating:** `POST /v1/omni_gen/cost/{image,video,audio,mesh,splat}` — public, no
auth. Use it to avoid burning credits.

---

## 6. Client library

`crates/api_clients/artcraft/artcraft_client` is a typed Rust client, but:

- It has **no `/v1/omni_api/*` wrappers.**
- Its `credentials` module is **cookie-only** — no bearer/API-key credential type.

So for the documented programmatic API you either hand-roll HTTP (recommended — it is 6
endpoints) or extend that crate. Do not build your gateway on `artcraft_client` for Omni API
traffic.

`support-tool artcraft generate_video` (`crates/cli/production/support-tool/`) is the closest
thing to an official CLI, but it is an internal ops tool using cookies against `/v1/omni_gen`, and
loads secrets from `.env-support-tool-secrets`. Not suitable for general use.

---

## 7. OpenAPI spec

**Generated, not committed.** To produce it locally:

```sh
SQLX_OFFLINE=true cargo run --bin docs-cli   # writes api.json
SQLX_OFFLINE=true cargo run --bin docs       # SwaggerUI on http://localhost:8989
```

Source of truth: `crates/service/web/storyteller_web/src/docs/api_doc.rs` — an
`#[derive(OpenApi)]` registry with ~350 handler paths and ~700 schemas, driven by `#[utoipa::path]`
attributes on each handler. Published at `https://storyteller-docs.netlify.app/`.

Because it is generated, **your gateway cannot read a checked-in spec**. Do runtime discovery
against `/v1/omni_gen/models/*` and `/v1/omni_gen/cost/*` instead, which are live and public.

---

## 8. How this fits the gateway

Add **one** app-level tool, `artcraft_cloud`, with a small surface:

```text
artcraft_cloud(action, params)
  action = models | cost | generate_image | generate_video | generate_audio
         | upload | job_status | list_media | download
```

and give it a **separate credential scope** — the cloud API key is a billing-bearing credential
and should never be reachable by the same tool call that edits a local document. Keep the
`Authorization` header out of logs (note: the server's own failure path logs the key at `warn!`
level — don't replicate that in your gateway).

Suggested split in the gateway:

| Tool | Credential | Sandbox |
|---|---|---|
| `artcraft_cloud` | cloud API key from gateway config, never from the agent | egress allow-list to `api.storyteller.ai` + `cdn-2.fakeyou.com`; credit budget per session |
| everything else | none (local processes) | filesystem roots |

---

## 9. Gotchas found

- Path constant drift: `CREATE_NEW_USER_ACCOUNT_AND_SUBSCRIPTION_CHECKOUT_URL_PATH` =
  `/v1/stripe_artcraft/user_signup/subscription_checkout` but the registered route is
  `/v1/stripe_artcraft/user_signup_subscription_checkout`. The registered route wins.
- The Postman collection's Production environment still points at `api.fakeyou.com`, and two
  requests target `/v1/control_plane/sora_secret`, which is not a registered route. Stale.
- `/v1/user_bookmarks/list/session` is commented out in the registrar.
- `artcraft_api_defs` holds ~105 route path constants — the best offline reference for building
  the client.
- The job-status handlers defensively filter the literal string `"None"` as a token, with the
  comment *"a bunch of Python clients use our API and can fail in this manner"*. Don't be one.
- `.env` in the repo root contains Stripe **test** keys and a development `NEWRELIC_API_KEY`
  marked as safe to commit. `secrets/` contains only `.gitkeep`.