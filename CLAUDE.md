# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Medas: a chat UI over a patient's own medical record, answered by a LangChain agent that retrieves from that record. Two independently developed packages — `medas-api` (FastAPI, Python 3.14, uv) and `medas-ui` (Next.js 16, React 19, Yarn 4). The root `README.md` is the single source of truth for setup, env vars, API surface, data model and known gaps; the package READMEs defer to it. Keep it in sync when changing a contract.

## Commands

API (run from `medas-api/`):

```bash
uv sync --group dev
uv run alembic upgrade head
uv run fastapi dev main.py                       # :8000, docs at /docs
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
uv run pytest tests/test_main.py::test_name -q   # single test
uv run python -m rag_pipeline.run                # build the Chroma index (billable embedding calls; needs OPENROUTER_API_KEY)
```

UI (run from `medas-ui/`):

```bash
yarn install
yarn dev                                         # :3000, needs the API running
yarn lint && yarn format:check && yarn tsc --noEmit && yarn test
yarn vitest run api/chat.test.ts -t "name"       # single test
yarn next typegen                                # needed before tsc on a fresh checkout (LayoutProps lives in .next)
```

Pre-commit hook (formats staged files with ruff / prettier, including all `.md`): `git config core.hooksPath .githooks`. CI (`.github/workflows/api.yml`, `ui.yml`) runs the same checks per package with `uv sync --locked` / `yarn install --immutable`, so relock after dependency changes.

## Architecture

- **The browser never calls the API.** `medas-ui` reaches `medas-api` only from the Next server: the page (Server Component) calls `GET /` via `api/init.ts`; the composer's Server Action calls `POST /ask` via `api/chat.ts`. `API_BASE_URL` is server-only on purpose — never add a `NEXT_PUBLIC_` variant.
- **Auth is Clerk; identity comes only from the token.** `medas-ui/proxy.ts` gates routes; `api/session.ts` attaches the session token as `Authorization: Bearer`. `medas-api/auth/session.py` (`current_user` dependency) verifies it and resolves/links/creates the `users` row. Never take the user from a request field. Every conversation query is scoped to the user in the same SQL statement, so another user's conversation is a 404.
- **One endpoint answers everything.** `POST /ask[?conversationId=]` (a thin route in `main.py` over `controller/`, which raises `NotFound` subclasses that one exception handler in `main.py` maps to 404) creates the conversation (seeding the greeting) or appends, and returns only the turns it added; the client appends them to a zustand store (`medas-ui/store/store.ts`).
- **Agent.** `controller/conversation.py` (`ask_question`) assembles the whole thread and calls `langchain_agent/agent.py` (`create_agent`, model `openai/gpt-4o-mini` via OpenRouter, system prompt in `agent/assistant_general_prompt.py`). Its single tool wraps `agent/search.py::search_record`, which queries a local Chroma collection. The patient id is passed as LangChain runtime context, not as a tool argument, so the model cannot choose whose record is read. The reply is JSON (`message`, `severity` S1–S5, `confidence`); prose replies are kept as-is without a badge.
  - JSON mode must be set via `extra_body={"response_format": ...}`, not `model_kwargs` — the latter trips the OpenAI SDK's strict-tool check.
- **RAG pipeline** (`rag_pipeline/`) chunks `medical_history.json` (each chunk repeats the patient identity line), embeds with `openai/text-embedding-3-small`, and stores in Chroma. Query-side embedding must use the same model. Embedding calls stay inside `run()` — importing must not fire them.
- **Persistence.** Async SQLAlchemy on asyncpg (`database/`), Alembic migrations in `migrations/versions/`. Messages are one row each, ordered by a global `seq` identity column (not timestamps, not per-conversation counters); writes use a single `INSERT ... SELECT ... FROM conversations WHERE ... AND NOT deleted` so the existence/ownership check is in the write itself.

## Testing conventions

Both suites are unit-only: no database, no model, no Clerk, no browser.

- API: patch `controller.conversation.ask_agent` (the one agent seam); override `current_user` in route tests. `tests/test_auth.py` uses real JWTs signed by a per-run RSA key. `conftest.py` clears the settings `lru_cache`s and sets a placeholder `CLERK_SECRET_KEY` — account for that when adding cached settings.
- UI: Vitest + jsdom + Testing Library. `api/chat.test.ts` stubs `globalThis.fetch` rather than mocking the module; component tests mock the API client. Response shapes live in `test/fixtures.ts`; `test/setup.ts` resets the store singleton between tests.

## Gotchas

- `medas-ui` uses a Next.js version newer than training data — read `medas-ui/AGENTS.md` and the docs in `node_modules/next/dist/docs/` before writing Next code. `next dev` rewrites the AGENTS.md block; commit it rather than reverting.
- Postgres driver is asyncpg (Windows event-loop constraints); pgvector is deliberately not used yet — embeddings live in Chroma.
- `.env` `DATABASE_*` values are composed with `URL.create()`; don't percent-encode the password.
- Formatting: ruff for Python; prettier (no semicolons, double quotes, trailing commas) for TS/CSS/JSON/Markdown.
