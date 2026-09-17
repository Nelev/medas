# Medas

A personal medical assistant: a chat UI over a patient's own medical history, answered with retrieval over that record rather than from the model's memory.

Two packages, deployed and developed separately:

| | | |
|---|---|---|
| [`medas-api`](medas-api) | FastAPI, Python 3.14 | Chat endpoints, Postgres persistence, the RAG pipeline |
| [`medas-ui`](medas-ui) | Next.js 16, React 19 | Chat interface |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — installs Python 3.14 itself, so no system Python is needed
- Node 20+ and Yarn
- Postgres 18 (any 13+ works; `gen_random_uuid()` is the only version-sensitive dependency)
- An [OpenRouter](https://openrouter.ai) key, for the embedding calls

## Setup

### Database

```bash
createdb medas
```

### API

```bash
cd medas-api
cp .env.example .env    # set DATABASE_PASSWORD
uv sync --group dev
uv run alembic upgrade head
```

The DSN is composed from the individual `DATABASE_*` variables via SQLAlchemy's `URL.create()`, which escapes the password — don't percent-encode it in `.env`.

### UI

```bash
cd medas-ui
yarn install
```

`API_BASE_URL` defaults to `http://localhost:8000`. It is read in Server Components only, so it is deliberately not `NEXT_PUBLIC_` — the backend origin never reaches the browser bundle.

## Running

```bash
cd medas-api && uv run fastapi dev main.py
```

```bash
cd medas-ui && yarn dev
```

API on `:8000` (docs at `/docs`), UI on `:3000`.

## Checks

```bash
cd medas-api && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

```bash
cd medas-ui && yarn lint && yarn tsc --noEmit
```

The Python suite is unit-only by design: no `.env` and no database, so it runs in CI unchanged. Anything needing a live Postgres belongs in a separate integration job. [`.github/workflows/api.yml`](.github/workflows/api.yml) runs lint, format and tests on every push and PR touching `medas-api/`.

## API surface

| Method | Path | |
|---|---|---|
| `GET` | `/` | Greeting for a user, before any conversation exists. Not persisted. |
| `POST` | `/conversations` | Starts a conversation, seeded with the greeting and the sender's first message. |
| `POST` | `/conversations/{id}/messages` | Appends a message. 404 if the conversation is unknown or soft-deleted. |
| `GET` | `/health/db` | Reports the Postgres server version. |
| `POST` | `/messages` | Echo stub from an earlier iteration. Unused. |

### Data model

`users` — id, email, role, timestamps.

`conversations` — id, FK to `users`, `messages` as a `jsonb` array, soft-delete flag, `updated_at`.

Messages live in a `jsonb` array rather than their own table: the whole history comes back in one read, which is exactly the shape the model is given. The cost is that Postgres rewrites the entire row on each append, so appending message N is roughly O(N). Fine for short conversations; the signal to move to a `messages` table keyed `(conversation_id, seq)` is conversations running long, or needing search, pagination, or per-message state.

Adding a message is a single `UPDATE ... SET messages = messages || :message`, never a read-modify-write in application code — two overlapping requests on one conversation would otherwise silently lose a message.

## RAG pipeline

[`medas-api/rag_pipeline`](medas-api/rag_pipeline) flattens a patient record into standalone chunks, embeds them with `openai/text-embedding-3-small` via OpenRouter, and stores them in a local Chroma collection.

```bash
cd medas-api
OPENROUTER_API_KEY=... uv run python -m rag_pipeline.run
```

Each chunk repeats the patient identity line, because retrieval hands the model one chunk with no surrounding document — "Reaction: rash" on its own names neither the patient nor the substance.

The embedding calls are billable, so they are behind `run()` rather than at module level: importing the module fires nothing.

## Status

Built: the chat UI, the conversation endpoints, the chunking and embedding pipeline with its Chroma index.

Not built yet:

- **No LLM wired to the chat.** Storing a message does not produce an answer; retrieval currently runs only in the standalone pipeline script.
- **No auth.** The user is a hardcoded constant in the UI, and `user_id` sits in the request body. It has to come from an authenticated session before this handles a real record.
- **Two identifiers for one user.** The API takes both a `users.id` and the opaque patient id the greeting is addressed to, because nothing maps between them. An `external_id` column on `users` collapses them.
- **The UI calls `/init`,** which has moved to `/`. The two halves are out of sync until that fetch is repointed.
- **pgvector is not installed.** Embeddings live in Chroma; moving them into Postgres needs a source build on Windows.
