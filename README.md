# Medas

A personal medical assistant: a chat UI over a patient's own medical history, answered with retrieval over that record rather than from the model's memory.

Two packages, deployed and developed separately:

|                          |                      |                                                       |
| ------------------------ | -------------------- | ----------------------------------------------------- |
| [`medas-api`](medas-api) | FastAPI, Python 3.14 | Chat endpoint, Postgres persistence, the RAG pipeline |
| [`medas-ui`](medas-ui)   | Next.js 16, React 19 | Chat interface                                        |

## How a message flows

Every request to medas-api is made by the Next server. The browser only ever talks to its own origin:

| Step          | Who calls                              | Call                                                            |
| ------------- | -------------------------------------- | --------------------------------------------------------------- |
| Page load     | The Next server, in a Server Component | `GET /[?user=…]` → the greeting, not persisted                  |
| Every message | The Next server, in a Server Action    | `POST /ask[?conversationId=…]` → stores the turn and answers it |

That is what keeps the API's origin out of the browser bundle, removes any need for CORS, and lets one build run in any environment.

Both steps need a signed-in user. [Clerk](https://clerk.com) handles the session: signed out, [`proxy.ts`](medas-ui/proxy.ts) redirects everything but `/sign-in` and `/sign-up` to the sign-in page, and the page and the Server Action each check the session again, since a Server Action is a POST endpoint anyone can call.

Every call to medas-api carries the user's Clerk session token as `Authorization: Bearer …`, and the API takes who is asking from that token alone — never from the request. [`auth/session.py`](medas-api/auth/session.py) verifies it (signature, expiry, and that it was issued for this site) and resolves it to a `users` row: by `users.clerk_user_id` once linked, and on the first sign-in by matching the account's **verified** primary email to an unclaimed row, or, when no row has that email, by creating one. Without a verified email the account is refused with `403`, since the row needs one. Every conversation read and write is scoped to that user in the same SQL statement, so someone else's conversation is a `404`, exactly like one that does not exist. Only `/health/db` is public.

One endpoint answers every message. `conversationId` is optional: without it the API starts a conversation and seeds the greeting, with it the message is appended to that thread. A caller that has just opened the app does not have to know which case it is in, so the composer has no branch — it passes whatever id it holds, which is empty on the first send. The id comes back in the response and lives in a client-side store.

The greeting addresses the signed-in user by their Clerk first name. [`greetingName()`](medas-ui/api/session.ts) reads it on the Next server, and the same name goes to `GET /` for the preview and to the `POST /ask` that starts a conversation, so the greeting stored is the one the patient already saw. An account with no first name sends none, and the API greets "Hi there".

Nothing is read back: the UI keeps the history it was given, so a reload starts from the greeting again.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — installs Python 3.14 itself, so no system Python is needed
- Node 20+ and Yarn 4 (pinned by `packageManager`; `corepack enable` honours it)
- Postgres 13 or newer — `gen_random_uuid()` is the only version-sensitive dependency
- An [OpenRouter](https://openrouter.ai) key. Answering a message means an embedding call per search and several model calls.

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

Any Clerk account gets a `users` row on its first sign-in, so this is not needed to use the app. It is how you sign in as the owner of the one medical record: the first sign-in links your Clerk account to the unclaimed row with the same verified email, instead of creating a new one.

The seed uses `pat_7f3c9a21+clerk_test@example.com`. In a Clerk development instance any `+clerk_test` address is a test address: no email is sent, and the verification code is always `424242`. Sign up with that address and code, and the account links on your first request. To use a real address instead, put it in the `INSERT` — it has to be one you can verify.

There is no seed script yet. Save this as `medas-api/seed.py` and run `uv run python seed.py` from `medas-api`:

```python
import asyncio

from sqlalchemy import text

from database.database import init_engine

SQL = """
INSERT INTO users (id, email)
VALUES ('7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0', 'pat_7f3c9a21+clerk_test@example.com')
ON CONFLICT DO NOTHING
"""


async def seed() -> None:
    engine = init_engine()
    async with engine.begin() as connection:
        await connection.execute(text(SQL))
    await engine.dispose()


asyncio.run(seed())
```

Already seeded with the old `pat_7f3c9a21@example.com`? `ON CONFLICT DO NOTHING` leaves it as it was, so update it once:

```sql
UPDATE users SET email = 'pat_7f3c9a21+clerk_test@example.com'
WHERE id = '7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0';
```

That `INSERT` works just as well through `psql` — note the Windows installer does not put the client on your `PATH`, which is why the Python route is given first.

### Build the vector index

The agent searches this to answer anything about the patient, so it has to exist first — an empty or absent Chroma store means no passages and an answer with nothing to cite. See [RAG pipeline](#rag-pipeline); it is one command, and it costs one batch of embedding calls.

### UI

```bash
cd medas-ui
yarn install
```

## Environment

| Variable                                                | Read by                                                                       | Default                     | If it is wrong                           |
| ------------------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------- | ---------------------------------------- |
| `API_BASE_URL`                                          | The Next **server** → `api/init.ts`, `api/chat.ts`                            | `http://localhost:8000`     | The page fails to render, and sends fail |
| `OPENROUTER_API_KEY`                                    | medas-api — embeddings and the model calls                                    | none                        | Answering fails; the API still starts    |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` | medas-ui — the Clerk session                                                  | none                        | Sign-in does not load                    |
| `CLERK_SECRET_KEY`                                      | medas-api — verifying session tokens, and the email lookup on a first sign-in | none                        | The API refuses to start                 |
| `CLERK_AUTHORIZED_PARTIES`                              | medas-api — the origins a token may be issued for, as a JSON list             | `["http://localhost:3000"]` | Every request is `401`                   |

The Clerk keys go in `medas-ui/.env.local`, and nobody needs to copy them by hand: `yarn dlx clerk@latest init` writes development keys there, for an unclaimed app when you are signed out of Clerk. `yarn dlx clerk@latest auth login` claims it later. The build does not need them, so CI runs without them. medas-api needs the same `CLERK_SECRET_KEY` in `medas-api/.env`; its tests use a placeholder and generate their own signing key, so its CI does not need it either.

`API_BASE_URL` has no `NEXT_PUBLIC_` counterpart on purpose. A `NEXT_PUBLIC_` value is inlined into the bundle at build time, so a built artefact would carry whatever URL the build machine had and the browser would call the API cross-origin. Read on the server at request time instead, it can be changed per environment without rebuilding.

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

Both suites are unit-only by design — no database, no API, no model, no browser — so they run unchanged in CI. `yarn test:watch` reruns on change.

## API surface

| Method | Path                                         | Request        | Response                                                         |
| ------ | -------------------------------------------- | -------------- | ---------------------------------------------------------------- |
| `GET`  | `/[?user=<name>]`                            | —              | `{messages: [{role, text}]}` — the greeting, not persisted       |
| `POST` | `/ask[?conversationId=<uuid>][&user=<name>]` | `{role, text}` | `201 {conversation_id, messages}` — the turns this request added |
| `GET`  | `/conversations/{id}`                        | —              | `{conversation_id, messages}` — the whole history, oldest first  |
| `GET`  | `/health/db`                                 | —              | `{status, server_version}`                                       |

`POST /ask` returns **what it added**, not the whole thread: three turns when it started the conversation (the greeting, the question, the answer) and two when it appended (the question and the answer). Either way the client appends them to what it already has.

Three things that trip people up: who is asking is the session token alone, never a request field; `user` is only the name the greeting addresses, an optional **query parameter** (1–200 characters, `"Hi there"` without one) that `POST /ask` reads only when it starts a conversation; and the message goes in the body **flat** — a `{message: {...}}` wrapper is a 422.

`message_id` and `timestamp` are minted server-side and ignored if sent. An assistant turn also carries `severity` (`S1`–`S5`) and `confidence` when the model returned them, stored with the message rather than returned alone: which triage code was given, and when, is what an audit asks about later. An unknown or soft-deleted conversation is a `404`, never an implicit create — that would resurrect deleted threads and let a caller choose its own primary key.

### How an answer is produced

The route does not run a tool loop of its own. It assembles the conversation, hands it to a LangChain agent, and stores what comes back.

1. **Assembles the turns.** Every stored message becomes `{role, content}` — the wire calls the field `text`, a chat model calls it `content` — and the new question goes last. The whole thread is sent, so the model answers in the context of everything said before rather than the last message alone.
2. **Runs the agent.** [`langchain_agent/agent.py`](medas-api/langchain_agent/agent.py) is a `create_agent` graph with one tool and [`agent/assistant_general_prompt.py`](medas-api/agent/assistant_general_prompt.py) as its system prompt. The graph decides for itself whether to search, how many times, and when it has enough to answer — which is the thing the hand-rolled loop this replaced could not do.
3. **Searches when it asks to.** The model cannot reach Chroma; only this process can, so a tool call is a question rather than an answer. `search_patient_record(query)` takes **only** a query: whose record is searched is fixed by the service, not chosen by the model, so a message claiming a different record id cannot become a read of somebody else's chart.
4. **Reads the reply.** The prompt specifies one JSON object, so the route parses it for `message` — what the patient sees — and stores `severity` and `confidence` as metadata.

The prompt triages rather than diagnoses: a ranked differential, an explicit confidence, clarifying questions whenever that confidence is not high, and a severity rated on the **worst plausible cause** rather than the most likely one. Red flags lead the reply and force `S1`.

The model is `openai/gpt-4o-mini`, named in [`langchain_agent/agent.py`](medas-api/langchain_agent/agent.py).

**The JSON is enforced by the transport, not just requested by the prompt.** `extra_body={"response_format": {"type": "json_object"}}` is on the chat model. That distinction cost real time and is worth recording: passing the same thing as `model_kwargs` does **not** work, because langchain routes through the OpenAI SDK's parsing helper whenever `response_format` is in the payload it builds, and that helper rejects any tool that is not `strict` (`search_patient_record is not strict`). `extra_body` reaches the provider without passing through that check.

Even so the model sometimes answers in prose — most often on a red flag, where it drops the format and writes the warning out directly. That reply is a good answer, so the route keeps it and shows it as it stands; only the triage code is lost with it, and the turn renders without a badge.

### Data model

`users` — id, email, role, timestamps.

`conversations` — id, FK to `users`, soft-delete flag, `created_at`.

`messages` — id, FK to `conversations`, `seq`, `role`, `content`, `metadata`, `created_at`.

Messages started out as a `jsonb` array on the conversation row. That shape returned the whole history in one read, which is exactly what the model is given, but Postgres has no in-place update: every append rewrote the entire row, so adding message N cost O(N) and every writer on that conversation queued behind the rewrite. One row per message makes an append constant-time and lets the history be read in pieces — ordered, counted, paginated, or filtered by role.

Ordering is `seq`, a **global** identity column, not a timestamp and not a per-conversation counter. `created_at` defaults to `clock_timestamp()` so it is distinct per row, but a counter still beats it: a counter cannot run backwards when the clock is stepped, and it is a stable pagination cursor — "everything after `seq` N" stays correct where "everything after instant T" can skip a row written a microsecond earlier by a slower transaction. A per-conversation `MAX(seq) + 1` would need a lock on the conversation row — putting back the serialisation this table removes — or a retry loop on the unique violation. A global counter leaves gaps between conversations, and the gaps mean nothing.

Every write — one appended message or the pair a new conversation is seeded with — goes through one statement: `INSERT ... SELECT ... FROM conversations WHERE ... AND NOT deleted`, fed from parallel arrays so the SQL text is fixed for any number of messages. The `SELECT` is the existence check, so it happens in the statement that writes rather than in one before it: no window between deciding to write and writing, and no rows selected means no rows inserted, which is how the caller learns the conversation was unknown or deleted. The same `WHERE` clause carries the ownership check — `c.user_id` is the signed-in user — so a conversation that is not the caller's matches nothing, exactly like one that does not exist.

`conversations.updated_at` is gone, renamed to `created_at`. It was only ever bumped because an append rewrote that row; appending now writes to `messages` alone, and bumping a column on the conversation would mean taking the lock this change exists to avoid. Last activity is `MAX(messages.created_at)`.

Moving the data is [`c3a5e1d97b24`](medas-api/migrations/versions/c3a5e1d97b24_add_messages_table.py), which backfills every existing array into rows, keeping the `message_id` and `timestamp` already stored, and reverses cleanly: `downgrade` rebuilds the arrays from the rows.

## RAG pipeline

[`medas-api/rag_pipeline`](medas-api/rag_pipeline) flattens a patient record into standalone chunks, embeds them with `openai/text-embedding-3-small` via OpenRouter, and stores them in a local Chroma collection.

```bash
cd medas-api
OPENROUTER_API_KEY=... uv run python -m rag_pipeline.run
```

Each chunk repeats the patient identity line, because retrieval hands the model one chunk with no surrounding document — "Reaction: rash" on its own names neither the patient nor the substance.

The embedding calls are billable, so they are behind `run()` rather than at module level: importing the module fires nothing.

The query side is [`agent/search.py`](medas-api/agent/search.py) — one function, `search_record(query, patient_id)`, which the agent's tool wraps. The `patient_id` is the signed-in user's, `pat_{users.id}`: `/ask` passes it to `answer()`, which hands it to the run as LangChain runtime context, so the tool reads it without it ever being a tool argument the model could set. An account with no indexed record gets no passages, and is told its record shows nothing relevant. It embeds the query with the same model the corpus was embedded with (Chroma's own MiniLM would be a different space, and the distances meaningless), filters on `patient_id` in the metadata, and returns each passage with its `chunk_id` and distance. Both halves stay off the event loop: the embedding is a real `await`, and the Chroma query — whose client is synchronous and embedded — runs in a thread.

## Testing

116 tests in medas-api, 36 in medas-ui.

The agent is stubbed at one seam. `main.ask_agent` is what every test patches, so the model, the tool, the prompt and the vector store all stay out of the suite — otherwise it would be slow, billable, non-deterministic, and impossible in CI where none of them exist. The fake records the turns it was given, which is how the history tests assert on what the agent was actually told.

Auth is split the same way. Route tests override `current_user`, so they run as a fixed user without Clerk. [`tests/test_auth.py`](medas-api/tests/test_auth.py) covers the dependency itself with real JWTs, signed by an RSA key generated for the run and verified by Clerk's SDK through its networkless `jwt_key` path: expired, not yet valid, another key, another site's `azp`, machine tokens, the email linking and its refusals. Nothing reaches Clerk.

On the frontend:

- [`medas-ui/api/chat.test.ts`](medas-ui/api/chat.test.ts) stubs `globalThis.fetch` rather than mocking the module, so URL building and response mapping actually run — every bug this file has had lived in exactly those two places. The Clerk session is mocked: the token goes out as a bearer header and never as a URL parameter, and `ask` refuses a signed-out caller before it reaches the API. It also covers when the greeting name is sent: on the first message only, and not at all without a first name.
- [`medas-ui/api/init.test.ts`](medas-ui/api/init.test.ts) covers the page-load call the same way: the name in `?user=`, left off when there is none, and a refused request thrown rather than rendered. Both files share the Clerk and `fetch` stubs in [`medas-ui/test/api.ts`](medas-ui/test/api.ts).
- [`medas-ui/components/chat/chat-composer.test.tsx`](medas-ui/components/chat/chat-composer.test.tsx) mocks the API client instead, and covers what the composer sends, what it does with the answer, and what it shows when a send fails. An `ask` held open by the test covers the wait in between: the message shown before the reply, handed over to its stored copy once, and no second send until then.
- [`medas-ui/components/chat/chat-messages.test.tsx`](medas-ui/components/chat/chat-messages.test.tsx) covers the list around that wait — the typing indicator up only while a message is pending, the greeting kept in view, and a scroll to the bottom when it grows. jsdom has no layout, so `scrollIntoView` and `matchMedia` are stubbed and the test asserts the call, not the scroll.

API response shapes live in `medas-ui/test/fixtures.ts`, so a contract change is a one-file edit. `test/setup.ts` resets the store before each test — it is a module singleton, so without that, whichever test ran first would decide the next one's result.

Two tests pin trade-offs rather than defects. The field is cleared optimistically on submit and stays cleared when the send fails, so retrying means retyping. And the whole thread is sent to the model unwindowed — asserted deliberately, so the cost is visible rather than accidental.

## CI

| Workflow                               | Runs on        | Steps                                               |
| -------------------------------------- | -------------- | --------------------------------------------------- |
| [`api.yml`](.github/workflows/api.yml) | `medas-api/**` | lint, format check, pytest                          |
| [`ui.yml`](.github/workflows/ui.yml)   | `medas-ui/**`  | lint, format check, typegen, typecheck, test, build |

One step in `ui.yml` exists for a non-obvious reason: **`next typegen`** before the typecheck. `LayoutProps` and friends are generated under `.next`, which a fresh checkout does not have, so `tsc` alone fails on `app/layout.tsx` and nothing else.

The build needs no API. `/` renders per request, so nothing is fetched while building — which is also what makes the artefact deployable: no greeting is baked in, and no API origin is compiled into the bundle.

## Troubleshooting

**Every request is 403.** `No verified email for this account`: the Clerk account's primary email is not verified. `This email belongs to another account`: a `users` row with that email is already linked to a different Clerk account. **Every request is 401.** The token did not verify: check `CLERK_SECRET_KEY` in `medas-api/.env` is the same key as the UI's, and that the UI's origin is in `CLERK_AUTHORIZED_PARTIES`.

**Sending shows a red banner.** The banner quotes the API's own error. `Failed to fetch` means the Next server could not reach medas-api — check `API_BASE_URL` and that the API is running.

**A submit reloads the page with `?message=…` in the URL.** The form was submitted before React hydrated, so the browser did a plain GET. Harmless, and it resolves once the page finishes loading.

**An answer arrives with no citations, saying the record does not cover it.** The Chroma index is missing or empty — build it with the RAG pipeline. The API does not fail without it; it answers from general knowledge and says so, which is harder to notice.

**A reply arrives with no severity badge.** The model answered in prose instead of the JSON the prompt asks for. The text is a real answer and is shown as-is; only the code is missing.

**Sending 500s.** Usually `OPENROUTER_API_KEY`: it is read when the agent's graph is first built, on the first request, so the API boots happily and fails on the first message. The agent has no error handling of its own, so anything the model call raises reaches the client as a 500.

**A reply takes a very long time, or fails with a context-length error.** The agent kept searching. Nothing bounds its loop — see Known gaps.

**`Cannot find name 'LayoutProps'`.** Route types have not been generated. Run `yarn next typegen`, or any `yarn dev` / `yarn build`.

**The dev server reports a module that no longer exists.** Turbopack caches a deleted file's import. Restart `yarn dev`.

## Status

Working end to end: the chat UI, one endpoint that starts a conversation or continues it, multi-turn answers grounded in the patient's record with the triage code rendered as a badge, Postgres persistence, and the chunking and embedding pipeline with its Chroma index.

### Known gaps

Safety and correctness first, because these are the ones that matter if this ever sees a real record.

- **Nothing bounds the agent's search loop.** `create_agent` defaults its recursion limit to 9,999, and the model will keep rephrasing a query it has already run. Observed: a single request accumulating ~112,000 tokens of passages — against a record that is ~2,400 tokens in total — until it exceeded the model's context window and the patient got nothing. Withdrawing the tool after a budget of searches is the fix that worked; a recursion limit alone stops the run but ends it without an answer.
- **The agent has no error handling.** `answer()` has no try/except, so a failed model call is a 500 rather than something the patient can act on.
- **The prompt documents a `<patient>` block that is never sent.** Its Inputs section describes identity and demographics arriving with each question; the route sends only the conversation. The model learns who the patient is from the identity line repeated in each retrieved chunk, which works but is not what the prompt says.
- **History is sent whole.** Every stored turn goes to the model on every request, and the transcript is re-sent on each turn within a run, so a long thread costs more with every message in it.
- **A search returns five passages.** `n_results=5`, so a question like "what episodes are in my record?" is answered from the five nearest chunks — the record holds ten episodes, and the model has no way to know it saw half of them.

Then the smaller ones:

- **No history on reload.** `GET /conversations/{id}` exists, but nothing calls it: the UI keeps the history it was given in memory, so a refresh returns to the greeting with the stored conversation orphaned.
- **Every page load waits on Clerk.** `greetingName()` calls `currentUser()`, a Clerk Backend API request, before the greeting is fetched — tens to hundreds of milliseconds on each render, for one string. A `firstName` claim on the session token would make it a local read, and would let the API resolve the name itself and drop the `user` parameter; it needs the claim added in the Clerk dashboard first.
- **No idempotency.** A double-submitted first message creates two conversations.
- **A submit before hydration is lost.** The composer uses an `onSubmit` handler rather than a form action, so a submission made before React hydrates navigates to `/?message=…` and the message is dropped. React queues submissions for a `<form action={…}>`; a plain handler cannot.
- **pgvector is not installed.** Embeddings live in Chroma; moving them into Postgres needs a source build on Windows.
