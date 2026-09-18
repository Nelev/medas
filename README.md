# Medas

A personal medical assistant: a chat UI over a patient's own medical history, answered with retrieval over that record rather than from the model's memory.

Two packages, deployed and developed separately:

|                          |                      |                                                        |
| ------------------------ | -------------------- | ------------------------------------------------------ |
| [`medas-api`](medas-api) | FastAPI, Python 3.14 | Chat endpoints, Postgres persistence, the RAG pipeline |
| [`medas-ui`](medas-ui)   | Next.js 16, React 19 | Chat interface                                         |

## How a message flows

Two different clients talk to the API, which is why there are two base-URL variables:

| Step                | Who calls                              | Call                                                                                                 |
| ------------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Page load           | The Next server, in a Server Component | `GET /?user=…` — the greeting, not persisted                                                         |
| First message       | The browser                            | `POST /conversations?userId=…` — creates the conversation, seeded with the greeting and this message |
| Every message after | The browser                            | `POST /conversations/{id}/messages` — appends                                                        |

The conversation id is held in a client-side store, which is how the composer knows which of the two calls to make. Nothing is read back: the UI keeps the history it was given, so a reload starts from the greeting again.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — installs Python 3.14 itself, so no system Python is needed
- Node 20+ and Yarn 4 (pinned by `packageManager`; `corepack enable` honours it)
- Postgres 13 or newer — `gen_random_uuid()` is the only version-sensitive dependency
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

### Seed the placeholder user

**Required, and easy to miss.** The UI sends a hardcoded `USER_ID` (see [`medas-ui/api/chat.ts`](medas-ui/api/chat.ts)), and `conversations.user_id` is a foreign key — so without a matching row, the first message of every conversation comes back `404 User not found`.

There is no seed script yet. Save this as `medas-api/seed.py` and run `uv run python seed.py` from `medas-api`:

```python
import asyncio

from sqlalchemy import text

from database.database import init_engine

SQL = """
INSERT INTO users (id, email)
VALUES ('7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0', 'pat_7f3c9a21@example.com')
ON CONFLICT DO NOTHING
"""


async def seed() -> None:
    engine = init_engine()
    async with engine.begin() as connection:
        await connection.execute(text(SQL))
    await engine.dispose()


asyncio.run(seed())
```

That `INSERT` works just as well through `psql` — note the Windows installer does not put the client on your `PATH`, which is why the Python route is given first.

### UI

```bash
cd medas-ui
yarn install
```

## Environment

| Variable                   | Read by                             | Default                 | If it is wrong                                     |
| -------------------------- | ----------------------------------- | ----------------------- | -------------------------------------------------- |
| `API_BASE_URL`             | The Next **server** — `api/init.ts` | `http://localhost:8000` | The page fails to render: `Failed to init profile` |
| `NEXT_PUBLIC_API_BASE_URL` | The **browser** — `api/chat.ts`     | `http://localhost:8000` | Sending fails silently (see Troubleshooting)       |

The `NEXT_PUBLIC_` prefix is what makes a variable reachable from the browser bundle. `init.ts` runs on the server and deliberately does not use one, so the backend origin stays out of the bundle.

Because the browser calls the API directly, the API keeps a CORS allowlist: `http://localhost:3000` and `http://127.0.0.1:3000`, in [`medas-api/main.py`](medas-api/main.py). **Serve the UI from any other port and every send is blocked** — add the origin there if you move it.

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
cd medas-ui && yarn lint && yarn format:check && yarn tsc --noEmit && yarn test
```

Both suites are unit-only by design — no database, no API, no browser — so they run unchanged in CI. `yarn test:watch` reruns on change.

## API surface

| Method | Path                           | Request                | Response                                                           |
| ------ | ------------------------------ | ---------------------- | ------------------------------------------------------------------ |
| `GET`  | `/?user=<id>`                  | —                      | `{messages: [{role, text}]}` — the greeting, not persisted         |
| `POST` | `/conversations?userId=<uuid>` | `{role, text}`         | `201 {conversation_id, messages}` — greeting **and** first message |
| `POST` | `/conversations/{id}/messages` | `{role, text}`         | `201 {role, text, message_id, timestamp}`                          |
| `GET`  | `/health/db`                   | —                      | `{status, server_version}`                                         |
| `POST` | `/messages`                    | `{message, user_name}` | Echo stub from an earlier iteration. Unused.                       |

Two things that trip people up: the owning user is a **query parameter** on create, not a body field, and the message goes in the body **flat** — a `{message: {...}}` wrapper is a 422.

`message_id` and `timestamp` are minted server-side and ignored if sent. An unknown or soft-deleted conversation is a `404` on append, never an implicit create — that would resurrect deleted threads and let a caller choose its own primary key.

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

## Testing

The frontend has 21 unit tests, in two files:

- [`medas-ui/api/chat.test.ts`](medas-ui/api/chat.test.ts) stubs `globalThis.fetch` rather than mocking the module, so URL building and response mapping actually run — every bug this file has had lived in exactly those two places.
- [`medas-ui/components/chat/chat-composer.test.tsx`](medas-ui/components/chat/chat-composer.test.tsx) mocks the API client instead, and covers which of the two calls the composer picks.

API response shapes live in `medas-ui/test/fixtures.ts`, so a contract change is a one-file edit. `test/setup.ts` resets the store before each test — it is a module singleton, so without that, whichever test ran first would decide the next one's result.

Two tests pin a defect rather than hiding it: `handleSubmit` has no `catch`, so a failed send is silent. They are commented to be deleted once it surfaces an error.

## CI

| Workflow                               | Runs on        | Steps                                 |
| -------------------------------------- | -------------- | ------------------------------------- |
| [`api.yml`](.github/workflows/api.yml) | `medas-api/**` | lint, format check, pytest            |
| [`ui.yml`](.github/workflows/ui.yml)   | `medas-ui/**`  | lint, typegen, typecheck, test, build |

Two steps in `ui.yml` exist for non-obvious reasons:

- **`next typegen`** before the typecheck. `LayoutProps` and friends are generated under `.next`, which a fresh checkout does not have, so `tsc` alone fails on `app/layout.tsx` and nothing else.
- **A stub API** before the build. `/` is prerendered, so `next build` fetches the greeting at build time and dies with `ECONNREFUSED` on a runner. [`scripts/stub-api.mjs`](medas-ui/scripts/stub-api.mjs) answers that one request.

That second one has a consequence worth stating plainly: **the CI build is not a deployable build.** The prerendered page carries the stub's greeting. A real deploy needs a reachable API at build time, or a page that renders per request.

## Troubleshooting

**The first message returns 404.** No `users` row matches the hardcoded `USER_ID` — see Seed the placeholder user.

**Sending does nothing and no error appears.** `handleSubmit` has no `catch`, so a rejected request vanishes; check the browser console. The usual cause is the UI running on a port outside the API's CORS allowlist.

**`Cannot find name 'LayoutProps'`.** Route types have not been generated. Run `yarn next typegen`, or any `yarn dev` / `yarn build`.

**The dev server reports a module that no longer exists.** Turbopack caches a deleted file's import. Restart `yarn dev`.

## Status

Working end to end: the chat UI, creating and appending messages, Postgres persistence, and the chunking and embedding pipeline with its Chroma index.

Not built yet:

- **No LLM wired to the chat.** Storing a message does not produce an answer — the assistant only ever speaks its opening greeting. Retrieval currently runs only in the standalone pipeline script.
- **No auth.** The user is a hardcoded constant in the UI and `userId` is a query parameter on a public endpoint. It must come from an authenticated session before this handles a real record.
- **The greeting is addressed to a hardcoded `"Mattia"`** in two places — `init.ts` ignores its own `user` argument, and `start_conversation` passes a literal — so the name shown has nothing to do with whose record is loaded.
- **`userId` is typed `str`, not `UUID`**, so a malformed id is a 500 from the driver rather than a 422.
- **No history on reload.** Nothing reads conversations back; there is no `GET` for them.
- **No idempotency.** A double-submitted first message creates two conversations.
- **pgvector is not installed.** Embeddings live in Chroma; moving them into Postgres needs a source build on Windows.
