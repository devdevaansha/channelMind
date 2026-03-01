# atva_transcriber — Implementation Plan

## Decisions Made
- **Backend**: Django
- **UI**: Django Templates + HTMX (SSE for live job progress)
- **Transcription**: faster-whisper (CTranslate2, GPU)
- **Database**: Local Postgres in docker-compose for local dev; `DATABASE_URL` env var points to Neon for VM/prod
- **Task queue**: Celery + Redis

---

## Directory / File Tree

```
atva_transcriber/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile.web
├── Dockerfile.worker
├── entrypoint_web.sh
├── entrypoint_worker.sh
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── web.txt          # extends base + gunicorn + gevent
│   └── worker.txt       # extends base + faster-whisper + yt-dlp (torch installed at runtime)
├── config/              # Django project package
│   ├── __init__.py
│   ├── celery.py
│   ├── gunicorn.py
│   ├── urls.py
│   ├── wsgi.py
│   └── settings/
│       ├── __init__.py
│       ├── base.py
│       ├── local.py
│       └── production.py
├── apps/
│   ├── __init__.py
│   ├── channels/        # Channel, Video, Category models + discover tasks
│   │   ├── admin.py, apps.py, forms.py, models.py, tasks.py, urls.py, views.py
│   │   └── migrations/
│   ├── jobs/            # Job, Artifact, VectorIndexItem models + SSE view
│   │   ├── admin.py, apps.py, models.py, urls.py, views.py
│   │   └── migrations/
│   ├── pipeline/        # Celery task chain
│   │   ├── apps.py, chains.py, progress.py
│   │   └── tasks/
│   │       ├── download.py    # Stage B: yt-dlp
│   │       ├── transcribe.py  # Stage C: faster-whisper
│   │       ├── upload.py      # Stage D: GCS
│   │       ├── categorize.py  # Stage E: Gemini classify
│   │       ├── summarize.py   # Stage F: Gemini summary (optional)
│   │       ├── embed.py       # Stage G: Vertex AI embeddings + chunk to disk
│   │       └── upsert.py      # Stage H: Pinecone upsert
│   ├── library/         # Library/transcript viewer
│   │   ├── apps.py, urls.py, views.py
│   └── search/          # Search tab
│       ├── apps.py, forms.py, urls.py, views.py
├── services/            # Framework-agnostic clients (no Django imports)
│   ├── ytdlp_client.py
│   ├── whisper_client.py
│   ├── gcs_client.py
│   ├── gemini_client.py
│   ├── vertex_client.py
│   └── pinecone_client.py
├── templates/
│   ├── base.html
│   ├── partials/
│   │   ├── nav.html, toast.html, progress_bar.html
│   ├── channels/
│   │   ├── index.html, _channel_row.html, _add_form.html
│   ├── jobs/
│   │   ├── index.html, _job_row.html, _job_detail_modal.html
│   ├── library/
│   │   ├── index.html, _video_card.html, detail.html
│   └── search/
│       ├── index.html, _result_item.html
├── static/
│   ├── css/app.css
│   └── js/
│       ├── htmx.min.js
│       ├── sse.js          # HTMX SSE extension
│       └── app.js          # progress bar updates, modal helpers
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_views/
    │   ├── test_channels.py, test_jobs.py, test_library.py, test_search.py
    ├── test_pipeline/
    │   ├── test_download.py, test_transcribe.py, test_upload.py
    │   ├── test_summarize.py, test_embed.py, test_upsert.py
    └── test_services/
        ├── test_gcs_client.py, test_gemini_client.py
        ├── test_vertex_client.py, test_pinecone_client.py
```

---

## Data Models

### apps/channels/models.py
- **Category**: `id (uuid pk)`, `name`, `created_by`, `created_at`
- **Channel**: `id (uuid pk)`, `youtube_channel_id (unique)`, `title`, `created_at`, `last_synced_at`, `sync_cursor`, `summarize_enabled (bool)`, `default_category (fk nullable)`
- **Video**: `id (uuid pk)`, `channel (fk)`, `youtube_video_id (unique)`, `title`, `published_at`, `duration_sec`, `status (enum: discovered|queued|processing|done|failed)`, `category (fk nullable)`, `auto_category_confidence`, `transcript_local_path`, `summary_local_path`, `gcs_prefix`, `created_at`, `updated_at`

### apps/jobs/models.py
- **Job**: `id (uuid pk)`, `video (fk)`, `pipeline_version`, `status (enum: queued|running|succeeded|failed|canceled)`, `stage (enum: fetch|download|transcribe|upload|categorize|summarize|embed|upsert)`, `progress (int 0-100)`, `error`, `created_at`, `updated_at`, `started_at`, `finished_at`
- **Artifact**: `id`, `video (fk)`, `type (enum: transcript_json|transcript_txt|summary_md|audio_wav|audio_m4a)`, `local_path`, `gcs_uri`, `sha256`, `created_at`
- **VectorIndexItem**: `id`, `video (fk)`, `pinecone_namespace`, `pinecone_vector_id`, `embedding_model`, `chunking_version`, `created_at`

---

## Pipeline Stages (Celery chain)

| Stage | Task | Progress weight |
|-------|------|----------------|
| A | `discover_channel_videos` (channels/tasks.py) | 5% |
| B | `download_audio` (yt-dlp) | 20% |
| C | `transcribe_audio` (faster-whisper GPU) | 35% |
| D | `upload_artifacts` (GCS) | 10% |
| E | `auto_categorize` (Gemini classify) | 5% |
| F | `summarize_video` (Gemini, optional) | 10% |
| G | `embed_chunks` (Vertex AI) | 10% |
| H | `upsert_to_pinecone` | 10% (→ 100%) |

Chain built in `apps/pipeline/chains.py` using `celery.chain` with `si()` immutable signatures. Summarize stage is conditionally included based on `channel.summarize_enabled`.

Progress is published to Redis pub/sub channel `job_progress:<job_id>` via `apps/pipeline/progress.py`. The SSE view (`apps/jobs/views.py`) subscribes and streams to the browser.

---

## Storage Layout

### Local (/data Docker volume)
```
/data/channels/<channel_id>/videos/<video_id>/
  source/      # audio.m4a
  transcript/  # transcript.json + transcript.txt
  summary/     # summary.md + summary.json (optional)
  chunks/      # chunk_0001.json … (text + embedding)
  logs/
```

### GCS
```
gs://<bucket>/youtube/channels/<channel_id>/
  channel.json
  videos/<video_id>/
    metadata.json
    transcript/transcript.json
    transcript/transcript.txt
    summary/summary.md         (optional)
    chunks/chunk_NNNN.json
```

---

## Docker Services

| Service | Image | GPU | Notes |
|---------|-------|-----|-------|
| `db` | postgres:16 | No | Local dev only; prod uses Neon |
| `redis` | redis:7-alpine | No | Broker + result backend + pub/sub |
| `web` | Dockerfile.web | No | Django + gunicorn (gevent workers) |
| `worker` | Dockerfile.worker | **Yes** | Celery worker, `--gpus all` |
| `beat` | Dockerfile.worker | No | Celery beat scheduler |
| `flower` | Dockerfile.worker | No | Celery monitoring UI on :5555 |

**GPU / torch handling**: `entrypoint_worker.sh` reads `nvidia-smi` driver version, maps it to a CUDA tag (cu118/cu121/cu124), installs the matching torch wheel, and caches it on the `torch_venv` Docker volume so subsequent starts are instant.

---

## Config (.env.example)

```
DATABASE_URL=postgresql://atva:atva@db:5432/atva
REDIS_URL=redis://redis:6379/0
GCS_BUCKET=
GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GEMINI_MODEL=gemini-2.5-flash-latest
VERTEX_PROJECT_ID=
VERTEX_REGION=us-central1
PINECONE_API_KEY=
PINECONE_INDEX=
PINECONE_ENV=
DATA_DIR=/data
YOUTUBE_API_KEY=     # optional; fallback uses yt-dlp flat playlist
DJANGO_SETTINGS_MODULE=config.settings.local
SECRET_KEY=change-me-in-production
DEBUG=true
```

Service account key is mounted read-only at `/secrets/sa.json` in both `web` and `worker` containers.

---

## Key Architectural Notes

**SSE streaming**: `apps/jobs/views.py` returns a `StreamingHttpResponse` backed by a Redis pub/sub generator. Requires gunicorn `worker_class = "gevent"` — sync workers will block on long-lived streams and exhaust the pool.

**Celery tasks use `si()` (immutable)**: Return values are NOT passed between pipeline stages. All inter-task communication goes through the database and `/data` filesystem. This prevents large payloads (embeddings, transcripts) from flowing through Redis.

**faster-whisper generator**: `model.transcribe()` returns a lazy generator. It must be consumed eagerly inside the task (iterated fully) to fire progress callbacks and avoid cross-thread issues.

**`QuerySet.update()` and `auto_now`**: Django's `auto_now` on `updated_at` is NOT triggered by `.update()` calls. Always pass `updated_at=tz.now()` explicitly in bulk updates.

**Pinecone metadata**: Each vector includes `text` (the ~30s chunk text), `video_id`, `channel_id`, `title`, `start`, `end`. Full transcript is NOT stored in metadata (40KB limit). Full text is in Postgres + local disk + GCS.

---

## UI Tabs

| Tab | URL | HTMX behavior |
|-----|-----|---------------|
| Channels | `/channels/` | Add form POSTs, new row prepended via `hx-swap="afterbegin"` |
| Jobs | `/jobs/` | Running jobs have `hx-ext="sse"` on the row; SSE messages update progress bar via `app.js` |
| Library | `/library/` | Filter form GETs reload video list; detail view loads transcript/summary inline |
| Search | `/search/` | Query input triggers `hx-get` on `keyup delay:400ms`; results swap `#results` div |

---

## Implementation Order

### Phase 1 — Skeleton (start here)
1. `config/` Django project: `settings/base.py`, `urls.py`, `celery.py`, `wsgi.py`, `gunicorn.py`
2. `requirements/base.txt`, `requirements/web.txt`, `requirements/worker.txt`
3. `.env.example`, `.gitignore`
4. `docker-compose.yml`, `Dockerfile.web`, `Dockerfile.worker`, `entrypoint_web.sh`, `entrypoint_worker.sh`
5. `manage.py`
6. Stub `apps/` with `apps.py` and empty `__init__.py` for each app
7. Verify `docker compose up` starts without errors

### Phase 2 — Models & Migrations
1. `apps/channels/models.py` — Category, Channel, Video
2. `apps/jobs/models.py` — Job, Artifact, VectorIndexItem
3. `makemigrations channels jobs` + `migrate`
4. Register all models in each `admin.py`

### Phase 3 — Service Layer
1. `services/ytdlp_client.py` — `list_channel_videos()`, `download()`
2. `services/whisper_client.py` — `transcribe()` with progress callback
3. `services/gcs_client.py` — `upload_file()`, `upload_json()`
4. `services/gemini_client.py` — `summarize()`, `classify_category()`
5. `services/vertex_client.py` — `embed_texts()` (batches of 5)
6. `services/pinecone_client.py` — `upsert_vectors()`, `query()`

### Phase 4 — Pipeline Tasks
1. `apps/pipeline/progress.py` — weights + `update_job_progress()` + Redis pub/sub publish
2. `apps/pipeline/tasks/download.py`
3. `apps/pipeline/tasks/transcribe.py`
4. `apps/pipeline/tasks/upload.py`
5. `apps/pipeline/tasks/categorize.py`
6. `apps/pipeline/tasks/summarize.py`
7. `apps/pipeline/tasks/embed.py`
8. `apps/pipeline/tasks/upsert.py`
9. `apps/pipeline/chains.py` — assemble chain, conditional summarize
10. `apps/channels/tasks.py` — `discover_channel_videos`, `sync_all_channels`

### Phase 5 — Views & Templates
1. `base.html` with tab nav, HTMX + SSE extension script tags
2. Channels: `index.html`, `_channel_row.html`, `_add_form.html`, `views.py`, `forms.py`, `urls.py`
3. Jobs: `index.html`, `_job_row.html`, SSE stream view, retry view
4. Library: filter list, video detail with transcript + summary viewer
5. Search: query form, results partial
6. Static: `htmx.min.js`, `sse.js`, `app.js` (progress bar update handler)

### Phase 6 — Tests
1. `tests/conftest.py` — pytest fixtures (Django DB, mock Redis, eager Celery)
2. Model tests
3. Pipeline task tests (mock all service clients)
4. View/SSE tests
5. Service client unit tests (mock external APIs)

### Phase 7 — Hardening
1. Celery task timeouts (`time_limit`) and retry policies per stage
2. Structured JSON logging to stdout (per `job_id` / `video_id`)
3. `/healthz/` endpoint
4. Idempotency guards: skip download if audio file + sha256 match, skip embed if chunk hash unchanged
5. Rate-limit wrappers on Gemini + Vertex clients

---

## Risks to Watch

1. **Gunicorn worker type** — must be `gevent`; sync workers block on SSE and starve the pool
2. **faster-whisper generator** — consume eagerly in `transcribe()`; never return the generator
3. **`QuerySet.update()` skips `auto_now`** — always pass `updated_at=tz.now()` explicitly
4. **Pinecone 40KB metadata limit** — store chunk text only, not full transcript
5. **Vertex AI quota** — 1,500 req/min default; batching (5 texts/call) keeps usage ~24 calls per 1hr video
6. **yt-dlp cursor ordering** — YouTube channel pages are newest-first; cursor breaks if channel sorted differently
7. **torch_venv volume** — if host GPU driver changes, delete the volume to force reinstall
8. **Redis pub/sub cleanup** — SSE view `finally` block must unsubscribe to avoid connection leaks
9. **Neon cold starts** — use `CONN_MAX_AGE=0` in prod so Neon handles connection pooling
